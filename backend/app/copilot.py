import os
import re
from typing import List, Dict, Any
from groq import Groq
from dotenv import load_dotenv
from .models import ForensicRecord
from .anomaly_rules import AnomalyDetector
from .gnn_engine import GNNEngine

load_dotenv()

class ForensicCopilot:
    def __init__(self, records: List[ForensicRecord]):
        self.records = records
        self.api_key = os.getenv("GROQ_API_KEY", "").strip()
        self.client = Groq(api_key=self.api_key) if self.api_key else None

    def _get_live_model_id(self) -> str:
        preferred = [
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
            "gemma2-9b-it"
        ]
        if not self.client:
            return "llama-3.1-8b-instant"
        try:
            available = [m.id for m in self.client.models.list().data]
            for p in preferred:
                if p in available:
                    return p
            for m in available:
                if not any(bad in m.lower() for bad in ["whisper", "guard", "orpheus", "vision", "audio", "embed"]):
                    return m
        except Exception:
            pass
        return "llama-3.1-8b-instant"

    def _build_compact_context(self, query: str = "") -> str:
        if not self.records:
            return "NO RECORDS INGESTED."

        q = query.lower()

        # 1. Top GNN Risk Rankings
        gnn_section = []
        try:
            gnn = GNNEngine(self.records)
            scores = gnn.compute_risk_scores()
            gnn_section.append("GNN_RISK: " + ", ".join([f"{s['entity']}={s['gnn_risk_score']*100:.0f}%({s['classification']})" for s in scores[:5]]))
        except Exception:
            pass

        # 2. Key Heuristic Alerts
        alert_section = []
        try:
            detector = AnomalyDetector(self.records)
            anomalies = detector.detect_all_anomalies()
            crit = [a for a in anomalies if a.get("severity") in ["CRITICAL", "HIGH"]][:8]
            alerts_to_show = crit if crit else anomalies[:8]
            for a in alerts_to_show:
                desc = a.get("description", "").replace("followed within", "<=").replace("transfer", "tx")
                alert_section.append(f"ALERT[{a.get('category')}]: {desc}")
        except Exception:
            pass

        # 3. Domain Slicing & Chronological Ordering
        is_money = any(k in q for k in ["bank", "money", "transfer", "laundering", "mule", "amount", "cash", "smurf"])
        is_call = any(k in q for k in ["call", "phone", "cdr", "caller", "tower"])
        is_geo = any(k in q for k in ["route", "gps", "location", "escape", "travel", "map", "city"])

        sorted_records = sorted(self.records, key=lambda r: r.timestamp)

        if is_money and is_call:
            # Query asking about both calls and money: provide early calls and seed transfers
            tel = [r for r in sorted_records if r.source_domain == "TELECOM"][:12]
            bnk = [r for r in sorted_records if r.source_domain == "BANKING"][:10]
            selected = sorted(tel + bnk, key=lambda r: r.timestamp)
        elif is_money:
            bnk = [r for r in sorted_records if r.source_domain == "BANKING"]
            bnk.sort(key=lambda r: (r.amount or 0), reverse=True)
            selected = bnk[:22]
        elif is_call or is_geo:
            selected = [r for r in sorted_records if r.source_domain == "TELECOM" or r.geo_lat is not None][:22]
        else:
            selected = sorted_records[:22]

        log_lines = []
        for r in selected:
            t = r.timestamp.strftime("%H:%M")
            p = r.primary_entity.value if r.primary_entity else "-"
            s = r.secondary_entity.value if r.secondary_entity else "-"
            amt = f" ₹{int(r.amount)}" if r.amount else ""
            ip = f" IP:{r.ip_address}" if r.ip_address else ""
            loc = f" GPS:({r.geo_lat:.2f},{r.geo_lon:.2f})" if r.geo_lat and r.geo_lon else ""
            log_lines.append(f"[{r.source_domain[:3]}|{t}] {p} -> {s} | {r.action}{amt}{ip}{loc}")

        context_payload = (
            "\n".join(gnn_section) + "\n" +
            "\n".join(alert_section) + "\n" +
            "LOGS:\n" + "\n".join(log_lines)
        )
        return context_payload[:3800]

    def _clean_response(self, text: str) -> str:
        if not text:
            return ""
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        if "<think>" in cleaned:
            cleaned = cleaned.split("<think>")[0]
        cleaned = re.sub(r"(?i)^(Here's a thinking process.*?\n\n|Thinking Process:.*?\n\n)", "", cleaned)
        return cleaned.strip()

    def answer_query(self, query: str) -> Dict[str, Any]:
        if not self.records:
            return {
                "answer": "⚠️ **No forensic evidence ingested.** Ingest evidence in the sidebar first.",
                "cited_records": []
            }

        if not self.client:
            return {
                "answer": "⚠️ **GROQ_API_KEY not detected.** Check your `.env` file.",
                "cited_records": []
            }

        compact_context = self._build_compact_context(query)
        active_model = self._get_live_model_id()

        system_prompt = (
            "You are the Lead Digital Forensics AI for Chandigarh Police.\n"
            "Analyze the provided forensic logs and alerts carefully.\n"
            "Directly answer the investigator's question with specific phone numbers, bank accounts, timestamps, amounts, and coordinates.\n"
            "Use Markdown tables and bullet points where helpful.\n"
            "Do NOT include internal monologue, thinking process tags, or greetings."
        )

        try:
            completion = self.client.chat.completions.create(
                model=active_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"EVIDENCE LOGS & ALERTS:\n{compact_context}\n\nINVESTIGATOR QUERY:\n{query}"}
                ],
                temperature=0.1,
                max_tokens=750
            )
            raw_response = completion.choices[0].message.content or ""
            cleaned_response = self._clean_response(raw_response)

            if not cleaned_response:
                cleaned_response = "Evidence reviewed. Please refine your query for specific entities or timestamps."

            # Dynamic citations matching the query domain
            q_low = query.lower()
            relevant_records = []
            for r in self.records:
                if any(w in q_low for w in ["bank", "money", "transfer", "laundering", "mule", "cash"]) and r.source_domain == "BANKING":
                    relevant_records.append(r)
                elif any(w in q_low for w in ["call", "phone", "cdr", "caller", "tower"]) and r.source_domain == "TELECOM":
                    relevant_records.append(r)
                elif any(w in q_low for w in ["social", "telegram", "ip", "signal", "handle"]) and r.source_domain == "SOCIAL":
                    relevant_records.append(r)

            target_records = relevant_records if relevant_records else self.records

            cited_records = []
            for r in target_records[:5]:
                sec = f" -> {r.secondary_entity.value}" if r.secondary_entity else ""
                amt = f" (INR {r.amount:,.0f})" if r.amount else ""
                cited_records.append({
                    "record_id": r.record_id,
                    "domain": r.source_domain,
                    "timestamp": r.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    "actor": r.primary_entity.value if r.primary_entity else "N/A",
                    "details": f"{r.action}{sec}{amt}"
                })

            return {
                "answer": cleaned_response,
                "cited_records": cited_records
            }
        except Exception as e:
            return {
                "answer": f"**Groq Inference Error:** {str(e)}",
                "cited_records": []
            }
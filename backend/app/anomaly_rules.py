from typing import List, Dict, Any
from .models import ForensicRecord
from bisect import bisect_left, bisect_right

class AnomalyDetector:
    def __init__(self, records: List[ForensicRecord]):
        self.records = records

    def detect_all_anomalies(self, max_alerts: int = 100) -> List[Dict[str, Any]]:
        anomalies = []
        anomalies.extend(self.detect_call_transfer_coordination(max_results=40))
        anomalies.extend(self.detect_smurfing_patterns(max_results=40))
        anomalies.extend(self.detect_shared_ip_cross_domain(max_results=20))
        return anomalies[:max_alerts]

    def detect_call_transfer_coordination(self, window_minutes: int = 15, max_results: int = 40) -> List[Dict[str, Any]]:
        alerts = []
        calls = sorted([r for r in self.records if r.source_domain == "TELECOM" and r.secondary_entity], key=lambda x: x.timestamp)
        txns = sorted([r for r in self.records if r.source_domain == "BANKING" and r.amount and r.amount >= 50000], key=lambda x: x.timestamp)

        if not calls or not txns:
            return []

        txn_times = [t.timestamp for t in txns]
        
        for call in calls:
            # Binary search time window (O(log N) instead of O(N*M))
            start_idx = bisect_left(txn_times, call.timestamp)
            for idx in range(start_idx, len(txns)):
                txn = txns[idx]
                time_diff = (txn.timestamp - call.timestamp).total_seconds() / 60.0
                if time_diff > window_minutes:
                    break
                alerts.append({
                    "alert_id": f"ALT-CALL-TXN-{len(alerts)+1}",
                    "severity": "CRITICAL",
                    "category": "COORDINATED_FINANCIAL_ACTION",
                    "description": f"Call from {call.primary_entity.value} followed within {int(time_diff)} mins by ₹{txn.amount:,.2f} transfer",
                    "primary_entity": call.primary_entity.value,
                    "linked_entity": txn.primary_entity.value,
                    "timestamp": txn.timestamp.isoformat()
                })
                if len(alerts) >= max_results:
                    return alerts
        return alerts

    def detect_smurfing_patterns(self, max_results: int = 40) -> List[Dict[str, Any]]:
        alerts = []
        txns = [r for r in self.records if r.source_domain == "BANKING" and r.amount]
        acc_map: Dict[str, List[ForensicRecord]] = {}
        for r in txns:
            acc_map.setdefault(r.primary_entity.value, []).append(r)

        for acc, acc_txns in acc_map.items():
            if len(acc_txns) >= 3:
                sorted_txns = sorted(acc_txns, key=lambda x: x.timestamp)
                first_ts = sorted_txns[0].timestamp
                last_ts = sorted_txns[-1].timestamp
                if (last_ts - first_ts).total_seconds() <= 3600:
                    total_out = sum(t.amount for t in sorted_txns if t.amount)
                    alerts.append({
                        "alert_id": f"ALT-SMURF-{len(alerts)+1}",
                        "severity": "HIGH",
                        "category": "MULE_FANOUT_SMURFING",
                        "description": f"Account {acc} performed {len(sorted_txns)} transfers totaling ₹{total_out:,.2f} in under 1h",
                        "primary_entity": acc,
                        "timestamp": last_ts.isoformat()
                    })
                    if len(alerts) >= max_results:
                        return alerts
        return alerts

    def detect_shared_ip_cross_domain(self, max_results: int = 20) -> List[Dict[str, Any]]:
        alerts = []
        ip_map: Dict[str, List[ForensicRecord]] = {}
        for r in self.records:
            if r.ip_address:
                ip_map.setdefault(r.ip_address, []).append(r)

        for ip, recs in ip_map.items():
            domains = set(r.source_domain for r in recs)
            if len(domains) > 1:
                entities = list(set(r.primary_entity.value for r in recs))
                alerts.append({
                    "alert_id": f"ALT-IP-CORR-{len(alerts)+1}",
                    "severity": "MEDIUM",
                    "category": "CROSS_DOMAIN_IP_MATCH",
                    "description": f"Shared IP {ip} links {len(entities)} entities across {', '.join(domains)}",
                    "primary_entity": ip,
                    "linked_entities": entities[:5],
                    "timestamp": recs[0].timestamp.isoformat()
                })
                if len(alerts) >= max_results:
                    return alerts
        return alerts
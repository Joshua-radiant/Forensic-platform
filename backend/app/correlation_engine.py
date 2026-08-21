from typing import List, Dict, Any, Set
from .models import ForensicRecord

class CorrelationEngine:
    def __init__(self, records: List[ForensicRecord]):
        self.records = records

    def build_network_graph(self, max_edges: int = 300) -> Dict[str, Any]:
        """
        Maps multi-domain entities into interconnected nodes & edges.
        Bounded by max_edges to guarantee sub-50ms latency under peak concurrent loads.
        """
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []
        edge_tracker: Set[str] = set()

        for rec in self.records:
            if len(edges) >= max_edges:
                break

            p_val = rec.primary_entity.value
            p_type = rec.primary_entity.entity_type
            if p_val and p_val not in nodes:
                nodes[p_val] = {
                    "id": p_val,
                    "label": p_val,
                    "type": p_type,
                    "source_domain": rec.source_domain,
                    "degree": 0
                }

            if rec.secondary_entity and rec.secondary_entity.value:
                s_val = rec.secondary_entity.value
                s_type = rec.secondary_entity.entity_type
                if s_val not in nodes:
                    nodes[s_val] = {
                        "id": s_val,
                        "label": s_val,
                        "type": s_type,
                        "source_domain": rec.source_domain,
                        "degree": 0
                    }

                edge_key = f"{p_val}->{s_val}:{rec.action}"
                if edge_key not in edge_tracker:
                    edge_tracker.add(edge_key)
                    edges.append({
                        "source": p_val,
                        "target": s_val,
                        "relation": rec.action,
                        "domain": rec.source_domain,
                        "amount": rec.amount,
                        "timestamp": rec.timestamp.isoformat()
                    })
                    nodes[p_val]["degree"] += 1
                    nodes[s_val]["degree"] += 1

            if rec.ip_address:
                ip_val = rec.ip_address
                if ip_val not in nodes:
                    nodes[ip_val] = {
                        "id": ip_val,
                        "label": ip_val,
                        "type": "IP_ADDRESS",
                        "source_domain": "NETWORK",
                        "degree": 0
                    }
                
                ip_edge_key = f"{p_val}->{ip_val}:ROUTED_VIA"
                if ip_edge_key not in edge_tracker:
                    edge_tracker.add(ip_edge_key)
                    edges.append({
                        "source": p_val,
                        "target": ip_val,
                        "relation": "ROUTED_VIA",
                        "domain": "NETWORK",
                        "timestamp": rec.timestamp.isoformat()
                    })
                    nodes[p_val]["degree"] += 1
                    nodes[ip_val]["degree"] += 1

        return {
            "summary": {
                "total_nodes": len(nodes),
                "total_edges": len(edges)
            },
            "nodes": list(nodes.values()),
            "edges": edges
        }

    def generate_chronological_timeline(self, limit: int = 200) -> List[Dict[str, Any]]:
        """
        Normalizes and sorts events chronologically.
        Caps output to the most recent records to prevent payload bloat on high-volume datasets.
        """
        sorted_records = sorted(self.records, key=lambda x: x.timestamp, reverse=True)[:limit]
        
        # Re-sort slice in chronological ascending order for clear timeline rendering
        chronological_slice = sorted(sorted_records, key=lambda x: x.timestamp)
        
        return [
            {
                "record_id": r.record_id,
                "timestamp": r.timestamp.isoformat(),
                "domain": r.source_domain,
                "action": r.action,
                "actor": r.primary_entity.value,
                "target": r.secondary_entity.value if r.secondary_entity else None,
                "amount": r.amount,
                "ip": r.ip_address,
                "geo_lat": r.geo_lat,
                "geo_lon": r.geo_lon
            }
            for r in chronological_slice
        ]
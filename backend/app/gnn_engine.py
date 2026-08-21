import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.data import Data
from torch_geometric.nn import GCNConv
from typing import List, Dict, Any
from .models import ForensicRecord

class ForensicGCN(nn.Module):
    def __init__(self, in_channels: int, hidden_channels: int, out_channels: int):
        super(ForensicGCN, self).__init__()
        self.conv1 = GCNConv(in_channels, hidden_channels)
        self.conv2 = GCNConv(hidden_channels, out_channels)

    def forward(self, x, edge_index, edge_weight=None):
        x = self.conv1(x, edge_index, edge_weight)
        x = F.relu(x)
        x = F.dropout(x, p=0.1, training=self.training)
        x = self.conv2(x, edge_index, edge_weight)
        return torch.sigmoid(x)  # Risk output between 0.0 and 1.0

class GNNEngine:
    def __init__(self, records: List[ForensicRecord]):
        self.records = records
        self.entity_map = {}
        self.reverse_entity_map = {}
        self.node_features = []
        self.edge_list = []
        self.edge_weights = []

    def _build_graph_tensors(self):
        """Encodes entity domain types, activity frequency, and transaction amounts into tensors."""
        entities = {}
        
        # 1. Collect entities and aggregate raw behavioral stats
        for r in self.records:
            for ent, role in [(r.primary_entity, "src"), (r.secondary_entity, "tgt")]:
                if ent and ent.value:
                    val = ent.value
                    if val not in entities:
                        entities[val] = {
                            "type": ent.entity_type,
                            "domain": r.source_domain,
                            "degree": 0,
                            "total_amount": 0.0,
                            "is_ip": 1.0 if "IP" in ent.entity_type else 0.0,
                            "is_bank": 1.0 if "BANK" in r.source_domain or "ACCOUNT" in ent.entity_type else 0.0,
                            "is_phone": 1.0 if "PHONE" in ent.entity_type or "TELECOM" in r.source_domain else 0.0,
                            "is_social": 1.0 if "SOCIAL" in r.source_domain or "HANDLE" in ent.entity_type else 0.0,
                        }
                    entities[val]["degree"] += 1
                    if r.amount:
                        entities[val]["total_amount"] += float(r.amount)

        self.entity_map = {name: idx for idx, name in enumerate(entities.keys())}
        self.reverse_entity_map = {idx: name for name, idx in self.entity_map.items()}

        if not self.entity_map:
            return None

        # 2. Build feature matrix X: [is_phone, is_bank, is_ip, is_social, normalized_degree, normalized_amount]
        feature_list = []
        max_deg = max([d["degree"] for d in entities.values()]) or 1.0
        max_amt = max([d["total_amount"] for d in entities.values()]) or 1.0

        for val, d in entities.items():
            feature_list.append([
                d["is_phone"],
                d["is_bank"],
                d["is_ip"],
                d["is_social"],
                d["degree"] / max_deg,
                min(d["total_amount"] / max_amt, 1.0)
            ])

        # 3. Build Edge Index & Edge Weights
        edge_indices = [[], []]
        weights = []

        for r in self.records:
            if r.primary_entity and r.secondary_entity:
                u = self.entity_map.get(r.primary_entity.value)
                v = self.entity_map.get(r.secondary_entity.value)
                if u is not None and v is not None:
                    # Bidirectional message passing
                    edge_indices[0].extend([u, v])
                    edge_indices[1].extend([v, u])
                    w = float(r.amount) / 10000.0 if r.amount else 1.0
                    weights.extend([w, w])

        x = torch.tensor(feature_list, dtype=torch.float)
        edge_index = torch.tensor(edge_indices, dtype=torch.long)
        edge_weight = torch.tensor(weights, dtype=torch.float) if weights else None

        return Data(x=x, edge_index=edge_index, edge_attr=edge_weight)

    def compute_risk_scores(self) -> List[Dict[str, Any]]:
        """Runs the GNN forward pass and produces ranked suspect risk scores."""
        if not self.records or len(self.records) == 0:
            return []

        data = self._build_graph_tensors()
        if not data or data.x.size(0) == 0:
            return []

        in_dim = data.x.size(1)
        model = ForensicGCN(in_channels=in_dim, hidden_channels=16, out_channels=1)
        model.eval()

        with torch.no_grad():
            risk_predictions = model(data.x, data.edge_index)

        results = []
        for idx, score_tensor in enumerate(risk_predictions):
            entity_name = self.reverse_entity_map[idx]
            raw_score = float(score_tensor.item())
            
            # Base node degree heuristics multiplier
            degree_boost = min(data.x[idx][4].item() * 0.3, 0.3)
            final_risk = min(max(raw_score + degree_boost, 0.05), 0.99)

            classification = "HIGH" if final_risk >= 0.70 else ("MEDIUM" if final_risk >= 0.40 else "LOW")

            results.append({
                "entity": entity_name,
                "gnn_risk_score": round(final_risk, 3),
                "classification": classification,
                "node_degree": int(data.x[idx][4].item() * 10)
            })

        # Sort descending by risk score
        results.sort(key=lambda x: x["gnn_risk_score"], reverse=True)
        return results
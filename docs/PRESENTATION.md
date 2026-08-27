# Decisionforge — Présentation complète

## Présentation
decisionforge est un registre immuable, hashé (SHA-256), auditable et rejouable.

## À quoi ça sert ? (problèmes réglés)
- **Décision prise sans critères explicites** → résolu par un dossier déterministe, ordre-indépendant
- **Alternative non évaluée puis contestée** → résolu par un dossier déterministe, ordre-indépendant
- **Audit qui demande "pourquoi ce choix ?" sans trace** → résolu par un dossier déterministe, ordre-indépendant

## Cas d'utilisation concrets
- Comité investissement: prouver que 3 alternatives ont été comparées sur 5 critères pondérés
- Architecture logicielle (ADR): justifier le choix d'une base de données
- Appel d'offres: couvrir chaque critère par une pièce justificative

## Exemples d'utilisation (API)
```bash
curl -X POST http://localhost:8000/v1/decision-coverage-dossiers -d '{"decision_ids": [...] }'
# → { "qualification": "COMPLETE|GAPPED|INSUFFICIENT|INCOMPATIBLE", "coverage_ratio": 0.94, ... }
```

## À quoi ça pourrait servir (futur / possibilités)
- Gouvernance ESG: tracer les arbitrages
- Conformité SOX: dossier de décision auditable
- Registre ADR d'entreprise versionné

## Pour qui ?
Devs, auditeurs, ops, chercheurs — qui ont besoin d'une preuve opposable, pas d'un verdict déclaratif.

## Problèmes réglés (détaillés)
- **Decisionforge** → - Preuve / dossier / trace non opposable → résolu par dossier immuable et hash SHA-256
- **Decisionforge** → - Verdict déclaratif sans justification → le dossier expose obligations, fournisseurs et ratios
- **Decisionforge** → - Chaînage caché ou lacune invisible → serveur recharge et recalcule indépendamment du client
- **Decisionforge** → - Tiers qui ne peut pas relancer → le dossier est public et rejouable sans clé client

## Exemples d'utilisation (scénarios réels)
- **Comité investissement** → le dossier sert de preuve technique (pas d'autorité déclarative)
- **Architecture logicielle (ADR)** → le dossier sert de preuve technique (pas d'autorité déclarative)
- **Appel d'offres (couverture critères)** → le dossier sert de preuve technique (pas d'autorité déclarative)



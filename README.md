> **Présentation → [docs/PRESENTATION.md](docs/PRESENTATION.md)** — à quoi ça sert, cas d'usages, usages futurs.

# DecisionForge V1.07

DecisionForge est un registre autonome de décisions traçables. Il fige un problème, ses alternatives,
ses critères pondérés et les observations sourcées dans un snapshot immuable, puis calcule côté serveur
une recommandation reproductible. La V1.01 mesure la robustesse d'une évaluation existante en
perturbant systématiquement les poids. La V1.02 compare deux snapshots évalués après avoir recalculé
leurs résultats côté serveur depuis les observations immuables. La V1.03 agrège de façon prudente
3 à 50 évaluations compatibles dans un dossier de consensus reproductible. La V1.04 mesure la
calibration historique de probabilités prédites confrontées à des résultats observés. La V1.05
mesure la stabilité chronologique de décisions évaluées sans accepter d'ordre ou de résultat client.
La V1.06 attribue ensuite les changements calculés aux critères et observations persistés. La V1.07
mesure enfin la couverture robuste des critères sur 2 à 100 évaluations compatibles.

## Nouveautés V1.07 : couverture robuste des critères

- entrée stricte limitée à 2 à 100 `evaluation_ids` persistés et uniques ;
- identité canonique indépendante de l'ordre client et chronologie serveur par date puis ID ;
- recalcul de chaque évaluation et vérification des hashes de décision et de résultat ;
- compatibilité stricte : même décision logique, méthode, alternatives et contrat complet des critères ;
- couverture par critère = part des alternatives possédant une observation au seuil de confiance requis ;
- synthèses par évaluation et par critère, critères communément couverts et lacunes explicites ;
- couverture minimale, moyenne et pire évaluation déterministe ;
- `COMPLETE` si tous les critères sont intégralement couverts dans toute la série ;
- `PARTIAL` si seuls des critères optionnels présentent des lacunes sans rendre l'évaluation non concluante ;
- `INSUFFICIENT` dès qu'une évaluation recalculée est non concluante ;
- `INCOMPATIBLE` sans agrégation si les contrats diffèrent ;
- snapshot immuable et idempotent, hashes de preuve/dossier et audit append-only ;
- aucune qualification ne certifie les sources ni n'autorise une action.

## Nouveautés V1.06 : attribution des changements

- entrée stricte limitée à 2 à 100 `evaluation_ids` persistés et uniques ;
- requête canonisée indépendamment de l'ordre, puis chronologie serveur par date et ID ;
- rechargement et recalcul des scores, statuts, recommandations, rangs et hashes ;
- compatibilité stricte de la décision logique, méthode, alternatives et contrat des critères ;
- contributions pondérées par observation et critère pour chaque transition ;
- critères dominants, alternatives gagnantes/perdantes, pire transition et score de complétude ;
- changements explicitement séparés entre expliqués et non expliqués ;
- `EXPLAINED` si toutes les transitions changées disposent d'une attribution complète ;
- `PARTIAL` si une attribution utilise une observation absente d'un côté ou reste incomplète ;
- `INSUFFICIENT` si une évaluation manque de preuves concluantes ;
- `INCOMPATIBLE` si les décisions ou contrats ne sont pas comparables ;
- aucune qualification ne constitue une causalité externe ou une autorisation d'action.

## Nouveautés V1.05 : stabilité décisionnelle chronologique

- entrée stricte limitée à 2 à 100 `evaluation_ids` persistés, uniques et sans ordre client ;
- identité de requête indépendante de l'ordre, puis tri serveur par `created_at` et enfin par ID ;
- rechargement, recalcul et vérification du hash de chaque évaluation avant l'analyse ;
- compatibilité obligatoire : même décision logique, méthode, alternatives et contrat complet des critères ;
- transitions de statut, recommandation et rang détaillées entre chaque paire chronologique ;
- taux de churn, plus longues séries, première/dernière recommandation, pire couverture et pire marge ;
- `STABLE` si aucun statut concluant ni aucune recommandation ne change ;
- `DRIFTING` dès qu'un statut concluant ou une recommandation change ;
- `INSUFFICIENT` si au moins une évaluation reste non concluante faute de preuve ;
- `INCOMPATIBLE` si les décisions, méthodes ou contrats ne sont pas comparables ;
- snapshot et preuves SHA-256 immuables, idempotents et audités une seule fois ;
- le dossier est descriptif et ne déclenche, n'approuve ni n'autorise aucune action.

## Nouveautés V1.04 : calibration décisionnelle

- chaque décision peut figer un `forecast_outcome` contenant une distribution de probabilités complète,
  l'alternative observée et les références distinctes de prédiction et de résultat ;
- la distribution doit reprendre exactement toutes les alternatives, rester dans `[0,1]` et sommer à 1 ;
- entrée du dossier limitée à 3 à 500 `evaluation_ids` persistés et uniques ;
- rechargement, recalcul et vérification du hash de chaque évaluation avant toute statistique ;
- compatibilité obligatoire de la décision, méthode, alternatives et contrat complet des critères ;
- 10 bins fixes : `[0 ; 0,1)`, ..., `[0,9 ; 1]`, le dernier incluant la confiance 1 ;
- Brier multiclasses normalisé : moyenne de `Σ(p-y)² / nombre d'alternatives` ;
- log loss utilisant la probabilité observée, plancher `10⁻⁹` et borne supérieure fixe à 20 ;
- erreur de calibration attendue pondérée par l'effectif des bins ;
- couverture : évaluations possédant à la fois probabilités et résultat / évaluations demandées ;
- résolution : variance pondérée des exactitudes de bins autour de l'exactitude globale ;
- pire bin : premier bin ayant l'écart absolu confiance/exactitude maximal ;
- `INCOMPATIBLE` si les décisions ou contrats diffèrent ;
- `INSUFFICIENT` si la couverture est incomplète ou si moins de 30 observations complètes sont disponibles ;
- `CALIBRATED` exige simultanément Brier ≤ 0,25, log loss ≤ 0,70, erreur de calibration ≤ 0,10
  et écart du pire bin ≤ 0,20 ;
- `MISALIGNED` est émis si l'échantillon est complet et suffisant mais qu'au moins un seuil est dépassé ;
- snapshot immuable, hashé, idempotent quel que soit l'ordre des identifiants et audité une seule fois ;
- aucune qualification, métrique ou action ne peut être fournie par le client ;
- `CALIBRATED` décrit seulement l'historique et n'autorise aucune décision automatique.

## Nouveautés V1.03 : dossier de consensus

- entrée limitée à une liste de 3 à 50 `evaluation_ids` uniques ;
- méthode serveur fixe `evaluation-consensus-v1` et ordre des identifiants canonisé ;
- recalcul de chaque évaluation depuis sa décision et ses observations immuables ;
- contrôle de l'intégrité entre résultat recalculé et hash stocké ;
- compatibilité obligatoire : même titre/problème de décision, méthode d'évaluation, alternatives et
  contrat complet des critères, poids et seuils compris ;
- fréquences de recommandation, part majoritaire et métriques par alternative ;
- moyennes de rang et de score, dispersions population, couverture minimale et admissibilité ;
- marge gagnante minimale calculée à partir des évaluations qui possèdent une recommandation unique ;
- `CONSENSUS` si les évaluations recommandent toutes la même alternative ;
- `STABLE_MAJORITY` si une alternative atteint au moins deux tiers sans aucune insuffisance ;
- `DIVIDED` sinon, y compris en cas d'égalité de fréquence ;
- `INSUFFICIENT` dès qu'une évaluation recalculée a des preuves insuffisantes ;
- `INCOMPATIBLE` si les décisions ou contrats diffèrent, sans agrégation trompeuse ;
- snapshot SHA-256 immuable, idempotent et audité une seule fois ;
- aucun gagnant, score, rang, verdict, résultat ou ordre d'action ne peut être fourni par le client ;
- le dossier reste descriptif et ne déclenche, n'approuve ni n'autorise aucune action.

## Nouveautés V1.02 : comparaison de décisions évaluées

- entrée limitée à `baseline_evaluation_id` et `candidate_evaluation_id` ; la méthode est fixée côté serveur ;
- refus de tout verdict, qualification, résultat, rang ou ordre d'action fourni par le client ;
- recalcul complet côté serveur des statuts, recommandations, rangs, scores, couvertures et marges ;
- contrôle de compatibilité des méthodes d'évaluation, alternatives et contrats de critères ;
- qualifications prudentes calculées : `CONSISTENT`, `CHANGED`, `INCOMPATIBLE` ou `INSUFFICIENT` ;
- `CONSISTENT` indique que statut, recommandation et rangs restent cohérents, même si des métriques évoluent ;
- `CHANGED` signale un changement de statut, de recommandation ou de classement ;
- `INCOMPATIBLE` interdit toute conclusion d'évolution si les contrats ne sont pas comparables ;
- `INSUFFICIENT` reste non concluant si au moins une évaluation recalculée manque de preuves requises ;
- écarts détaillés par alternative : rang, score, couverture, admissibilité et marge du gagnant ;
- snapshot hashé, immuable, idempotent et inscrit une seule fois dans l'audit append-only ;
- aucune comparaison ne déclenche, n'approuve ou n'autorise automatiquement une action.

## Nouveautés V1.01 : sensibilité des poids

- politique serveur `bounded-oat-10pct-v1` : chaque poids diminue puis augmente de 10 %, un critère à la fois ;
- renormalisation déterministe des poids après chaque perturbation ;
- recalcul complet du statut, du classement, du gagnant et de sa marge pour chaque scénario ;
- qualification prudente calculée par le serveur : `ROBUST`, `FRAGILE` ou `INSUFFICIENT` ;
- `ROBUST` exige un gagnant de référence unique, au moins deux critères, le même gagnant dans tous les
  scénarios et une marge minimale d'au moins 1 point ;
- `FRAGILE` signale qu'une perturbation change le gagnant, supprime la recommandation unique ou réduit
  la marge sous le garde-fou prudent de 1 point ;
- `INSUFFICIENT` est utilisé si la référence n'a pas de gagnant unique ou si la sensibilité n'est pas mesurable ;
- le snapshot contient tous les scénarios, les raisons, la stabilité du gagnant, la marge minimale et un hash SHA-256 ;
- rejouer la même analyse renvoie le même snapshot immuable et n'ajoute pas de faux événement d'audit ;
- aucune qualification, aucun gagnant et aucune action ne peuvent être fournis par le client ;
- l'analyse n'exécute et n'autorise automatiquement aucune décision.

## Garanties cumulatives

- le client ne peut fournir ni verdict, ni classement, ni gagnant ;
- les poids sont normalisés par le moteur et le score est calculé avec `poids × observation × confiance` ;
- une observation requise absente ou sous le niveau de confiance minimal produit `INSUFFICIENT` ;
- si toutes les alternatives franchissent un seuil bloquant, le résultat est `BLOCKED` ;
- une meilleure alternative admissible unique produit `RECOMMENDED` ;
- une égalité en tête reste `INSUFFICIENT` : DecisionForge n'invente pas de certitude ;
- chaque entrée et sortie possède un hash SHA-256 canonique ;
- rejouer la même évaluation renvoie le même enregistrement ;
- les snapshots, évaluations et événements d'audit ne peuvent être ni modifiés ni supprimés ;
- Pydantic refuse tous les champs inconnus (`extra=forbid`) ;
- les comparaisons ne font jamais confiance aux résultats stockés sans les vérifier par recalcul.
- les consensus sont indépendants de l'ordre des identifiants et ne créent aucun faux audit au rejeu.
- les dossiers de calibration distinguent systématiquement insuffisance, incompatibilité et désalignement.
- les dossiers chronologiques recalculent les preuves et ignorent tout ordre proposé par le client.
- les dossiers de couverture distinguent complétude, lacunes, insuffisance et incompatibilité.

Une recommandation est conditionnelle aux observations fournies. Elle ne certifie ni leurs sources,
ni leur actualité, ni l'absence de facteurs externes. La décision finale reste humaine.

## Arborescence

Guides complémentaires : [exemples d'utilisation](docs/USAGE_EXAMPLES.md) et [contribution](CONTRIBUTING.md).

```text
decisionforge/
├── docs/openapi.yaml
├── docs/postgresql-schema.sql
├── scripts/Setup-DecisionForge.ps1
├── scripts/Start-DecisionForge.ps1
├── scripts/Test-DecisionForge.ps1
├── src/decisionforge/
└── tests/
```

## Installation sous Windows / PowerShell 7

```powershell
Set-Location .\decisionforge
.\scripts\Setup-DecisionForge.ps1
.\scripts\Start-DecisionForge.ps1
```

Documentation interactive : <http://127.0.0.1:8014/docs>

Pour utiliser une autre base SQLite :

```powershell
$env:DECISIONFORGE_DB = "D:\Data\decisionforge.sqlite3"
.\scripts\Start-DecisionForge.ps1
```

## Exemple minimal

Créer un snapshot avec `POST /v1/decisions` :

```json
{
  "title": "Choisir un hébergeur",
  "problem": "Quel hébergeur utiliser pour le service critique ?",
  "alternatives": [
    {"key": "alpha", "label": "Alpha"},
    {"key": "beta", "label": "Beta"}
  ],
  "criteria": [
    {"key": "reliability", "label": "Fiabilité", "weight": 0.7, "blocking_minimum": 60},
    {"key": "cost", "label": "Coût", "weight": 0.3}
  ],
  "observations": [
    {"alternative_key": "alpha", "criterion_key": "reliability", "score": 90, "confidence": 0.9, "source_ref": "audit-2026-08"},
    {"alternative_key": "alpha", "criterion_key": "cost", "score": 60, "confidence": 0.9, "source_ref": "devis-alpha"},
    {"alternative_key": "beta", "criterion_key": "reliability", "score": 70, "confidence": 0.9, "source_ref": "audit-2026-08"},
    {"alternative_key": "beta", "criterion_key": "cost", "score": 80, "confidence": 0.9, "source_ref": "devis-beta"}
  ],
  "forecast_outcome": {
    "predicted_probabilities": {"alpha": 0.8, "beta": 0.2},
    "observed_alternative_key": "alpha",
    "prediction_ref": "prévision-2026-08",
    "outcome_ref": "résultat-vérifié-2026-09"
  }
}
```

Puis demander le calcul, sans verdict client, avec `POST /v1/evaluations` :

```json
{"decision_id": "ID_RETOURNE", "method": "weighted-evidence-v1"}
```

Analyser ensuite sa sensibilité avec `POST /v1/sensitivity-analyses` :

```json
{
  "evaluation_id": "ID_EVALUATION",
  "method": "weight-sensitivity-v1",
  "policy": "bounded-oat-10pct-v1"
}
```

Le résultat est descriptif : `ROBUST` ne signifie pas que les données sont vraies ou que l'action est sans risque.

Comparer enfin deux évaluations avec `POST /v1/decision-comparisons` :

```json
{
  "baseline_evaluation_id": "ID_EVALUATION_BASELINE",
  "candidate_evaluation_id": "ID_EVALUATION_CANDIDATE"
}
```

La qualification obtenue décrit les différences calculées. Elle ne constitue jamais une autorisation d'agir.

Créer un dossier de consensus avec `POST /v1/consensus-dossiers` :

```json
{
  "evaluation_ids": [
    "ID_EVALUATION_1",
    "ID_EVALUATION_2",
    "ID_EVALUATION_3"
  ]
}
```

La majorité affichée est une mesure descriptive des résultats recalculés, jamais une décision automatique.

Créer un dossier de calibration avec `POST /v1/calibration-dossiers` :

```json
{
  "evaluation_ids": [
    "ID_EVALUATION_1",
    "ID_EVALUATION_2",
    "ID_EVALUATION_3"
  ]
}
```

Avec moins de 30 observations complètes, le résultat reste volontairement `INSUFFICIENT`.

Créer un dossier de stabilité avec `POST /v1/decision-stability-dossiers` :

```json
{"evaluation_ids": ["ID_EVALUATION_2", "ID_EVALUATION_1"]}
```

Le serveur canonise la requête, recharge les preuves et restitue sa propre chronologie. Les détails
complets d'installation et d'appels sont dans [docs/USAGE_EXAMPLES.md](docs/USAGE_EXAMPLES.md).

Créer un dossier d'attribution avec `POST /v1/decision-change-attribution-dossiers` :

```json
{"evaluation_ids": ["ID_EVALUATION_2", "ID_EVALUATION_1"]}
```

Le serveur renvoie les contributions par observation/critère, les critères dominants et les
transitions expliquées ou partielles. Il ne produit aucun ordre d'action.

## API

- `GET /health`
- `GET /info`
- `POST /v1/decisions`
- `GET /v1/decisions`
- `GET /v1/decisions/{decision_id}`
- `POST /v1/evaluations`
- `GET /v1/evaluations/{evaluation_id}`
- `POST /v1/sensitivity-analyses`
- `GET /v1/sensitivity-analyses/{analysis_id}`
- `POST /v1/decision-comparisons`
- `GET /v1/decision-comparisons/{comparison_id}`
- `POST /v1/consensus-dossiers`
- `GET /v1/consensus-dossiers/{dossier_id}`
- `POST /v1/calibration-dossiers`
- `GET /v1/calibration-dossiers`
- `GET /v1/calibration-dossiers/{dossier_id}`
- `POST /v1/decision-stability-dossiers`
- `GET /v1/decision-stability-dossiers`
- `GET /v1/decision-stability-dossiers/{dossier_id}`
- `POST /v1/decision-change-attribution-dossiers`
- `GET /v1/decision-change-attribution-dossiers`
- `GET /v1/decision-change-attribution-dossiers/{dossier_id}`
- `GET /v1/audit-events`

## Tests

```powershell
.\scripts\Test-DecisionForge.ps1
```

Le script exécute les tests réels et `compileall`. Le contrat statique OpenAPI 3.1 est aussi contrôlé par la suite de tests.


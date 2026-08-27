# Exemples d'utilisation de DecisionForge V1.07

## À quoi sert le projet ?

DecisionForge fige des décisions structurées et leurs observations sourcées, puis calcule côté
serveur une recommandation reproductible. Il permet aussi d'étudier la sensibilité des poids, de
comparer des évaluations, de mesurer un consensus, d'examiner une calibration historique et de
décrire la stabilité chronologique d'une série d'évaluations compatibles et attribuer les changements
aux observations et critères persistés, puis mesurer leur couverture sur toute la série.

Les résultats restent descriptifs. Aucun endpoint ne déclenche, n'approuve ou n'autorise une action.

## Installation sous PowerShell 7

```powershell
Set-Location .\decisionforge
.\scripts\Setup-DecisionForge.ps1
.\scripts\Start-DecisionForge.ps1
```

Le service écoute par défaut sur `http://127.0.0.1:8014`. Pour choisir une base SQLite :

```powershell
$env:DECISIONFORGE_DB = "D:\Data\decisionforge.sqlite3"
.\scripts\Start-DecisionForge.ps1
```

## Vérifier le service

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8014/health"
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8014/info"
```

Les deux réponses exposent la version `1.0.7`. `/info` indique aussi
`criterion-coverage-dossier-v1` et `automatic_action: false`.

## Créer puis évaluer deux snapshots compatibles

Une série chronologique utilise des snapshots distincts décrivant le même titre/problème, les mêmes
alternatives et le même contrat de critères. Les observations ou leur contexte peuvent évoluer.

```powershell
$Decision = @{
  title = "Choisir un hébergeur"
  problem = "Quel hébergeur utiliser ?"
  context = "Mesure du mois 1"
  alternatives = @(
    @{ key = "alpha"; label = "Alpha" },
    @{ key = "beta"; label = "Beta" }
  )
  criteria = @(
    @{ key = "reliability"; label = "Fiabilité"; weight = 0.7; blocking_minimum = 60 },
    @{ key = "cost"; label = "Coût"; weight = 0.3 }
  )
  observations = @(
    @{ alternative_key = "alpha"; criterion_key = "reliability"; score = 90; confidence = 0.9; source_ref = "audit-m1-a" },
    @{ alternative_key = "alpha"; criterion_key = "cost"; score = 60; confidence = 0.9; source_ref = "devis-m1-a" },
    @{ alternative_key = "beta"; criterion_key = "reliability"; score = 70; confidence = 0.9; source_ref = "audit-m1-b" },
    @{ alternative_key = "beta"; criterion_key = "cost"; score = 80; confidence = 0.9; source_ref = "devis-m1-b" }
  )
} | ConvertTo-Json -Depth 8

$Snapshot1 = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8014/v1/decisions" `
  -ContentType "application/json" -Body $Decision
$Evaluation1 = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8014/v1/evaluations" `
  -ContentType "application/json" -Body (@{ decision_id = $Snapshot1.id } | ConvertTo-Json)
```

Créez ensuite un second snapshot compatible avec un autre `context`, de nouvelles `source_ref` et
les observations plus récentes, puis évaluez-le pour obtenir `$Evaluation2`.

## Créer le dossier chronologique V1.05

Le client fournit uniquement des IDs. Même si la liste est inversée, le serveur la trie par
`created_at`, puis par ID en cas d'égalité.

```powershell
$Body = @{ evaluation_ids = @($Evaluation2.id, $Evaluation1.id) } | ConvertTo-Json
$Dossier = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8014/v1/decision-stability-dossiers" `
  -ContentType "application/json" -Body $Body

$Dossier.qualification
$Dossier.chronological_evaluation_ids
$Dossier.transitions
$Dossier.churn_rate
```

- `STABLE` : aucune recommandation ni aucun statut concluant ne change ;
- `DRIFTING` : au moins une recommandation ou un statut concluant change ;
- `INSUFFICIENT` : une preuve ne permet pas une évaluation concluante ;
- `INCOMPATIBLE` : la décision logique, la méthode, les alternatives ou les critères diffèrent.

Un changement de rang est toujours exposé dans `transitions`, même lorsqu'il ne change pas à lui seul
la qualification. Le rapport contient également les longueurs de séries, la première et dernière
recommandation, la pire couverture, la pire marge et trois hashes reproductibles.

## Relire ou lister les dossiers

```powershell
Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:8014/v1/decision-stability-dossiers/$($Dossier.id)"
Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:8014/v1/decision-stability-dossiers"
```

## Attribuer les changements V1.06

Le même ensemble d'IDs peut être envoyé dans n'importe quel ordre : le serveur recharge les preuves,
vérifie les hashes et reconstruit la chronologie. Il calcule ensuite la variation de la composante
`poids × score × confiance / somme des poids` pour chaque observation.

```powershell
$AttributionBody = @{
  evaluation_ids = @($Evaluation2.id, $Evaluation1.id)
} | ConvertTo-Json

$Attribution = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8014/v1/decision-change-attribution-dossiers" `
  -ContentType "application/json" -Body $AttributionBody

$Attribution.qualification
$Attribution.dominant_criteria
$Attribution.winning_alternatives
$Attribution.losing_alternatives
$Attribution.worst_transition
$Attribution.transitions[0].observation_contributions
$Attribution.transitions[0].unexplained_reasons
```

- `EXPLAINED` : toutes les transitions changées sont attribuées à des observations comparables ;
- `PARTIAL` : au moins une contribution est incomplète, par exemple une observation optionnelle
  présente dans un seul snapshot ;
- `INSUFFICIENT` : une évaluation recalculée manque de preuves requises ;
- `INCOMPATIBLE` : décision logique, méthode, alternatives ou contrat de critères différents.

```powershell
Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:8014/v1/decision-change-attribution-dossiers/$($Attribution.id)"
Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:8014/v1/decision-change-attribution-dossiers"
```

L'attribution explique le calcul interne. Elle ne prouve pas une causalité réelle extérieure aux
données persistées et ne déclenche, n'approuve ni n'autorise une action.

## Mesurer la couverture des critères V1.07

Le client ne fournit que les deux à cent IDs. Le serveur recalcule les résultats, vérifie leur
intégrité et mesure, pour chaque critère, la part des alternatives disposant d'une observation dont
la confiance atteint le seuil du contrat.

```powershell
$CoverageBody = @{
  evaluation_ids = @($Evaluation2.id, $Evaluation1.id)
} | ConvertTo-Json

$Coverage = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8014/v1/criterion-coverage-dossiers" `
  -ContentType "application/json" -Body $CoverageBody

$Coverage.qualification
$Coverage.common_covered_criterion_keys
$Coverage.gap_criterion_keys
$Coverage.minimum_overall_coverage
$Coverage.worst_evaluation
$Coverage.criteria
```

- `COMPLETE` : tous les critères sont couverts pour toutes les alternatives et évaluations ;
- `PARTIAL` : une lacune optionnelle subsiste sans rendre les évaluations non concluantes ;
- `INSUFFICIENT` : au moins une évaluation recalculée est non concluante ;
- `INCOMPATIBLE` : aucune agrégation n'est effectuée entre contrats différents.

```powershell
Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:8014/v1/criterion-coverage-dossiers/$($Coverage.id)"
Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:8014/v1/criterion-coverage-dossiers"
```

Une couverture complète vérifie la présence et la confiance minimale des observations ; elle ne
prouve ni l'exactitude, ni l'actualité, ni l'indépendance des sources.

## Exécuter les tests

```powershell
.\scripts\Test-DecisionForge.ps1
```

Le script exécute la suite cumulative puis `compileall`. Le workflow GitHub Actions effectue les
mêmes contrôles sous Linux et Windows avec Python 3.10 et 3.12.

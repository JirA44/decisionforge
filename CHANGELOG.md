# Changelog DecisionForge

## V1.07 — 1.0.7

- Ajout des dossiers déterministes `criterion-coverage-dossier-v1` pour 2 à 100 évaluations.
- Recalcul serveur, contrôle des hashes et tri chronologique indépendant de l'ordre client.
- Compatibilité stricte de la décision logique, méthode, alternatives et critères.
- Couverture par critère et alternative au regard du seuil de confiance persisté.
- Ajout des critères communs, lacunes, couvertures minimale/moyenne et pire évaluation.
- Qualifications prudentes `COMPLETE`, `PARTIAL`, `INSUFFICIENT`, `INCOMPATIBLE`.
- API POST/GET/list, SQLite/PostgreSQL et OpenAPI 3.1 exact alignés sur 1.0.7.
- Snapshot immuable, idempotent, hashé et audité ; aucune action automatique.

## V1.06 — 1.0.6

- Dossiers d'attribution pour 2 à 100 évaluations compatibles et chronologiques.
- Ordre serveur, recalcul des scores/rangs/recommandations et vérification des hashes.
- Contributions pondérées par critère et observation aux deltas de chaque alternative.
- Critères dominants, alternatives gagnantes/perdantes, pire transition et complétude d'explication.
- Qualifications prudentes `EXPLAINED`, `PARTIAL`, `INSUFFICIENT`, `INCOMPATIBLE`.
- Entrée IDs uniquement, snapshots immuables, idempotents, hashés et audités.
- API POST/GET/list, SQLite/PostgreSQL, OpenAPI 3.1, documentation et CI alignés sur 1.0.6.
- Attribution descriptive seulement : aucune causalité externe ni action automatique.

## V1.05 — 1.0.5

- Ajout du dossier chronologique de stabilité pour 2 à 100 évaluations persistées.
- Entrée limitée aux IDs uniques ; ordre, verdict, résultat et action client interdits.
- Recalcul des évaluations, vérification des hashes et tri serveur par date puis identifiant.
- Compatibilité stricte de la décision logique, méthode, alternatives et critères.
- Transitions de statut, recommandation et rang, churn, séries, première/dernière recommandation,
  pire couverture et pire marge.
- Qualifications prudentes `STABLE`, `DRIFTING`, `INSUFFICIENT`, `INCOMPATIBLE`.
- Snapshots ordre-indépendants, immuables, idempotents, hashés et audités.
- API POST/GET/list, SQLite/PostgreSQL, OpenAPI 3.1, documentation et CI alignés sur 1.0.5.
- Aucun automatisme d'action ; maintien intégral des capacités V1.00 à V1.04.

## V1.04 — 1.0.4

- Ajout des prédictions probabilistes et résultats observés immuables dans les snapshots de décision.
- Ajout des dossiers `decision-calibration-v1` pour 3 à 500 évaluations persistées uniques.
- Recalcul serveur et vérification des hashes avant toute mesure de calibration.
- Ajout de 10 bins déterministes, du Brier normalisé, de la log loss bornée, de l'ECE,
  de la couverture, de la résolution et du pire bin.
- Ajout des qualifications strictes `CALIBRATED`, `MISALIGNED`, `INSUFFICIENT`, `INCOMPATIBLE`.
- Seuil minimal fixé à 30 observations complètes et seuils de calibration publics et fixes.
- Idempotence indépendante de l'ordre, snapshot SHA-256 et audit append-only.
- Ajout des routes POST, GET et liste `/v1/calibration-dossiers`.
- Extension de SQLite, PostgreSQL, OpenAPI 3.1, `/info`, PowerShell et des tests cumulatifs.
- Aucun verdict client, aucune recommandation automatique et aucune action automatique.

## V1.03 — 1.0.3

- Ajout des dossiers déterministes `evaluation-consensus-v1` pour 3 à 50 évaluations uniques.
- Entrée limitée aux identifiants, avec refus des gagnants, scores, rangs, verdicts, résultats et actions clients.
- Rechargement et recalcul serveur de toutes les évaluations depuis les observations immuables.
- Vérification de la décision, de la méthode, des alternatives et des contrats complets de critères.
- Ajout des fréquences, majorité, rangs/scores moyens, dispersions, marges et couvertures minimales.
- Ajout des qualifications `CONSENSUS`, `STABLE_MAJORITY`, `DIVIDED`, `INSUFFICIENT`, `INCOMPATIBLE`.
- Idempotence indépendante de l'ordre des identifiants, hash canonique et audit append-only.
- Ajout des routes `POST /v1/consensus-dossiers`, `GET /v1/consensus-dossiers/{dossier_id}` et `GET /info`.
- Extension de SQLite, PostgreSQL, OpenAPI 3.1, PowerShell et des tests cumulatifs.
- Aucun automatisme d'action ; maintien intégral des capacités V1.00 à V1.02.

## V1.02 — 1.0.2

- Ajout de la comparaison déterministe `decision-comparison-v1` entre une évaluation baseline et candidate.
- Recalcul côté serveur des deux résultats depuis les observations immuables avant toute comparaison.
- Contrôle de compatibilité des méthodes, alternatives et contrats de critères.
- Comparaison des statuts, recommandations, rangs, scores, couvertures, admissibilités et marges.
- Ajout des qualifications prudentes `CONSISTENT`, `CHANGED`, `INCOMPATIBLE` et `INSUFFICIENT`.
- Ajout d'explications déterministes par changement, sans automatisme d'action.
- Ajout des snapshots de comparaison hashés, immuables, idempotents et audités.
- Ajout des routes `POST /v1/decision-comparisons` et `GET /v1/decision-comparisons/{comparison_id}`.
- Extension des schémas SQLite/PostgreSQL, du contrat OpenAPI 3.1 et des tests.
- Maintien intégral des fonctions V1.00 et V1.01.

## V1.01 — 1.0.1

- Ajout de l'analyse déterministe de sensibilité d'une évaluation existante.
- Ajout de la politique versionnée `bounded-oat-10pct-v1` : perturbations relatives −10 % et +10 %,
  un critère à la fois, puis renormalisation.
- Ajout des scénarios détaillés, de la stabilité du gagnant et de la marge minimale.
- Ajout des qualifications serveur prudentes `ROBUST`, `FRAGILE` et `INSUFFICIENT`, avec garde-fou
  de marge minimale fixé à 1 point pour `ROBUST`.
- Ajout des snapshots immuables et idempotents, du hash SHA-256 et de l'audit append-only.
- Ajout des routes `POST /v1/sensitivity-analyses` et `GET /v1/sensitivity-analyses/{analysis_id}`.
- Extension des schémas SQLite et PostgreSQL et du contrat OpenAPI 3.1.
- Maintien intégral des fonctions V1.00 de snapshots, évaluations, classements et audit.

## V1.00 — 1.0.0

- Première version du registre immuable de décisions.
- Évaluation `weighted-evidence-v1`, seuils bloquants et traitement prudent des preuves insuffisantes.

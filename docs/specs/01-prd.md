# SAAMSTIAHF — Système Agentique d'Analyse Médicale Sécurisée et Traçable par IA et Hyperledger Fabric — PRD

| Owner | Status | Version | Last updated | Suite version | Approvers |
|---|---|---|---|---|---|
| Équipe projet (4 membres) | Approved — vision et périmètre validés par l'encadrant (D-15) ; plan recalé (D-17) | 2.0.1 | 2026-10-23 | 2.1.4 | Encadrant pédagogique `[TBD: nom]` |

Source : cahier des charges « Projet 1 » ([Projet 1.md](../../Projet%201.md)).

## 1. Résumé

SAAMSTIAHF est un prototype pédagogique qui analyse un ECG 12 dérivations et son rapport médical par IA, valide le résultat par règles, hache chaque artefact intermédiaire (SHA-256) et ancre ces empreintes et leur provenance sur Hyperledger Fabric, le tout orchestré par des agents LangGraph — afin de pouvoir prouver a posteriori quelles données, quel prétraitement, quel modèle et quelle validation ont conduit à un résultat, et détecter toute modification ultérieure. Un volet matériel en VHDL sur carte Zybo Z7-10 (FPGA Zynq-7010) réimplémente deux maillons du pipeline — le hachage SHA-256 et le filtrage/décimation FIR de l'ECG — et prouve par co-vérification qu'ils produisent exactement les mêmes résultats que le logiciel.

## 2. Contexte et pourquoi maintenant

Les systèmes d'IA médicale produisent des résultats dont la provenance est difficile à démontrer après coup : quelle donnée, quel prétraitement, quelle version de modèle, quel contrôle. Le mini-projet (année universitaire 2026, 8 semaines) doit démontrer qu'un registre permissionné (Hyperledger Fabric) peut rendre ce processus inspectable et infalsifiable sans y stocker de donnée médicale. La blockchain n'analyse rien : elle protège la traçabilité et l'intégrité du processus d'IA.

Le projet comporte en plus un volet VHDL (D-10) : une seconde implémentation, matérielle et indépendante, du hachage et du prétraitement renforce la preuve (deux implémentations distinctes donnent les mêmes empreintes) et montre comment ces étapes pourraient être déportées sur un circuit dédié.

## 3. Utilisateurs cibles

- **Primaire — Opérateur d'analyse** (rôle `operator`) : téléverse un ECG et un rapport, lance l'analyse, consulte prédiction, validation et résultat final.
- **Secondaire — Auditeur** (rôle `auditor`) : consulte l'historique d'un cas, vérifie l'intégrité des artefacts, ne peut pas lancer d'analyse.
- **Secondaire — Administrateur** (rôle `admin`) : gère les comptes (S-08) et la configuration (seuils de validation, version du modèle active) en ligne de commande (`scripts/registry.py`, D-17).
- **Indirect — Jury / encadrant** : assiste à la démonstration (§9 du cahier des charges, étendue d'une étape matérielle, D-13).
- **Interne — Équipe projet** : conçoit, simule et exécute sur carte les modules VHDL et leur banc de co-vérification (US-15 à US-17).

## 4. Problème

- **Point de douleur :** impossible de prouver après coup qu'un résultat d'IA découle bien de telle donnée, tel prétraitement et telle version de modèle, ni de détecter qu'un fichier stocké a été altéré.
- **Contournement actuel :** journaux applicatifs et fichiers sur disque, modifiables par quiconque y a accès ; aucune preuve indépendante.
- **Preuves :** énoncé du cahier des charges (§1). `[TBD: références bibliographiques sur la traçabilité de l'IA médicale pour le rapport final]`.
- **Alternatives :** journaux signés centralisés, horodatage RFC 3161, blockchains publiques (inadaptées : coût, confidentialité). Fabric est imposé par le sujet.

## 5. Objectifs et indicateurs de succès

| Metric | Baseline | Target | Timeframe |
|---|---|---|---|
| Taux de détection des artefacts falsifiés (suite de tests d'intégrité) | N/A (nouveau système) | 100 % des artefacts modifiés détectés, 0 faux positif | 2026-11-30 (soutenance) |
| Couverture de traçabilité : artefacts d'un cas ancrés sur Fabric | N/A | 7/7 types d'artefact (§5 du CDC) pour 100 % des cas terminés | 2026-11-30 |
| Performance du modèle (PTB-XL, 5 superclasses, fold 10) | N/A | AUC macro ≥ 0,85 (D-09) | M3 (≤ 2026-11-15) |
| Durée du pipeline de bout en bout (un cas) | N/A | ≤ 60 s sur la machine de démo | M5 (≤ 2026-11-25) |
| Démonstration (§9 du CDC + étape matérielle) | N/A | 9/9 étapes du scénario réussies en une prise (D-13) | 2026-11-30 |
| Co-vérification logiciel ↔ matériel (SHA-256 et FIR) | N/A | 100 % des vecteurs identiques bit à bit, en simulation et sur carte | M3 (simulation, ≤ 2026-11-15), M4 (carte, ≤ 2026-11-20) |

- **Guardrail metrics :** aucune donnée médicale brute ni identifiant direct sur la chaîne (0 occurrence, vérifié par test) ; aucun cas « Accepté » si un contrôle d'intégrité amont échoue.

## 6. Fonctionnalités

Priorités : P0 = requis pour la soutenance, P1 = important, peut suivre, P2 = bonus.

| ID | Feature | User benefit | Priority |
|---|---|---|---|
| F-01 | Ingestion ECG + rapport avec pseudonymisation | Entrée unique, aucun identifiant personnel dans le pipeline | P0 |
| F-02 | Préparation des données ECG | Signal propre et normalisé + rapport de traitement | P0 |
| F-03 | Analyse IA (classification) | Classe prédite et probabilités, versionnées | P0 |
| F-04 | Validation par règles | Statut Accepté / Révision requise / Rejeté justifié | P0 |
| F-05 | Explication et résultat final | Résultat compréhensible et motivé | P0 |
| F-06 | Hachage SHA-256 de chaque artefact | Empreinte vérifiable de chaque étape | P0 |
| F-07 | Stockage hors chaîne chiffré | Données sensibles protégées hors blockchain | P0 |
| F-08 | Ancrage sur Hyperledger Fabric (chaincode) | Preuve immuable des empreintes et de la provenance | P0 |
| F-09 | Orchestration agentique (LangGraph) | Pipeline automatique, gestion des erreurs, journal des agents | P0 |
| F-10 | Historique de provenance d'un cas | Chaîne complète donnée originale → résultat final | P0 |
| F-11 | Vérification d'intégrité | Statut valide / modifié / manquant / non vérifiable par artefact | P0 |
| F-12 | Tableau de bord web | Interface simple pour tout le scénario de démo | P0 |
| F-13 | Authentification et rôles | Seuls les utilisateurs/services autorisés agissent | P0 |
| F-14 | Kit de démonstration et tests d'intégrité | Scénario de falsification reproductible, cas de test livrables | P0 |
| F-15 | Contrôle de cohérence ECG ↔ rapport par mots-clés | Règle « cohérence » exigée par le CDC §4.4 (D-01) | P0 |
| F-16 | Explication du signal (carte de saillance sur l'ECG) | Explication visuelle de la prédiction | P1 — non planifiée en v1 (D-17) |
| F-17 | Rédaction de l'explication par LLM | Texte plus naturel | P2 |
| F-18 | Cœur SHA-256 en VHDL sur Zybo Z7-10 | Seconde implémentation, matérielle, du hachage (CDC §4.5) | P0 (D-10) |
| F-19 | Filtre FIR passe-bas + décimation de l'ECG en VHDL sur Zybo Z7-10 | Prétraitement (CDC §4.2) accéléré en matériel, bit-exact | P0 (D-10) |
| F-20 | Banc de co-vérification logiciel ↔ matériel | Preuve d'équivalence reproductible (simulation + carte) et démonstrable | P0 (D-10) |

## 7. Hors périmètre v1

- Diagnostic clinique, usage sur patients réels (prototype pédagogique, CDC §10).
- Données EEG, IRM, analyse multimodale image/texte (extensions futures CDC §11).
- Modèles LSTM, ARIMA, Markov, transformeurs ; estimation avancée d'incertitude (CDC §11).
- Revue clinique et approbation signée numériquement par un médecin (CDC §11).
- Réseau Fabric multi-machines / production ; un réseau de test local suffit.
- Ré-entraînement du modèle depuis l'interface.
- Import direct depuis un dossier patient (DPI) ou un appareil ECG.
- Volet matériel : utilisation de la carte **dans le pipeline en ligne** (le pipeline ne dépend jamais de la carte ; co-vérification hors ligne uniquement, D-11) ; accélérateur du modèle CNN ; filtre passe-haut 0,5 Hz, normalisation et autres étapes en matériel ; PYNQ/Linux embarqué ; reconfiguration partielle ; ancrage on-chain des résultats de co-vérification.

## 8. Parcours utilisateur

1. L'opérateur se connecte.
2. Il crée un cas en téléversant un ECG (enregistrement WFDB PTB-XL ou CSV) et un rapport texte ; les identifiants sont retirés et un identifiant de cas pseudonymisé est attribué.
3. L'orchestrateur enchaîne automatiquement : préparation → caractéristiques → prédiction → validation → explication → résultat final ; chaque artefact est stocké hors chaîne, haché et ancré sur Fabric.
4. L'écran du cas affiche la progression en direct, puis la prédiction, la confiance, le statut de validation, l'explication, les empreintes et les identifiants de transaction.
5. L'auditeur ouvre l'historique du cas et lance une vérification d'intégrité.
6. (Démo) Un fichier stocké est modifié ; la vérification le signale « modifié ».
7. (Démo, étape matérielle) La carte Zybo Z7-10 recalcule l'empreinte d'un artefact et filtre une dérivation du cas ; les résultats sont identiques au registre et à l'artefact `processed` (US-15 à US-17).

Maquettes : voir App Flow ([06-app-flow.md](06-app-flow.md)) et Design Brief ([07-design-brief.md](07-design-brief.md)).

## 9. User stories et critères d'acceptation

### US-01 — Téléverser un ECG et un rapport (F-01)
En tant qu'opérateur, je veux téléverser un ECG et son rapport, afin de lancer l'analyse d'un cas.

- **AC-01.1** Given un opérateur connecté, when il soumet un ECG valide (WFDB `.hea`+`.dat` ou CSV 12 colonnes) et un rapport texte, then un cas est créé avec le statut `en_attente`, passe à `en_cours` dès que le pipeline le prend en charge, et le pipeline démarre.
- **AC-01.2** Given un fichier ECG de format non supporté, ou un téléversement (ECG + rapport) > 20 Mo au total, ou un enregistrement de moins de 10 s, when il le soumet, then la soumission est refusée avec un message indiquant le format/limite, et aucun cas n'est créé.
- **AC-01.3** Given un rapport absent, when il soumet uniquement l'ECG, then le cas est créé et la règle de cohérence de validation sera « non applicable ».

### US-02 — Pseudonymiser le cas (F-01)
En tant qu'opérateur, je veux que les identifiants personnels soient supprimés avant traitement, afin qu'aucune donnée identifiante n'entre dans le pipeline.

- **AC-02.1** Given un ECG dont l'en-tête/métadonnées contiennent un nom, une date de naissance ou un identifiant patient, when le cas est créé, then ces champs sont supprimés et un identifiant de cas pseudonymisé unique (`CASE-` + UUID) est attribué.
- **AC-02.2** Given deux soumissions du même patient, when les cas sont créés, then ils reçoivent deux identifiants de cas distincts (pas de lien patient conservé côté application).
- **AC-02.3** Given un rapport contenant un nom propre détecté, when le cas est créé, then le nom est remplacé par `[ANONYMISÉ]` dans la donnée originale stockée.

### US-03 — Préparer la donnée ECG (F-02)
En tant qu'opérateur, je veux que l'ECG soit vérifié et nettoyé automatiquement, afin que le modèle reçoive une donnée exploitable.

- **AC-03.1** Given un ECG valide, when la préparation s'exécute, then le système produit la donnée traitée (filtrée, normalisée, rééchantillonnée au format du modèle) et un rapport de traitement listant chaque opération et ses paramètres ; l'étage passe-bas + décimation 500 → 100 Hz utilise le modèle à virgule fixe identique au module matériel F-19 (version des coefficients indiquée dans le rapport).
- **AC-03.2** Given un ECG avec > 10 % d'échantillons manquants/invalides sur une dérivation, when la préparation s'exécute, then le score de qualité est marqué « insuffisant » dans le rapport de traitement (utilisé par la validation).
- **AC-03.3** Given un fichier illisible, when la préparation échoue, then le cas passe au statut `rejeté` avec la raison « préparation impossible » et l'échec est journalisé.

### US-04 — Obtenir une prédiction (F-03)
En tant qu'opérateur, je veux voir la classe prédite et le score de confiance, afin de connaître le résultat de l'analyse.

- **AC-04.1** Given une donnée traitée, when l'analyse s'exécute, then l'artefact de prédiction contient : classe(s) prédite(s), probabilités par classe (NORM, MI, STTC, CD, HYP), nom et version du modèle, identifiant de l'artefact d'entrée, horodatage.
- **AC-04.2** Given le résultat disponible, when l'opérateur ouvre le cas, then la classe principale et sa confiance (en %) sont affichées.
- **AC-04.3** Given le fichier du modèle introuvable ou corrompu (empreinte du modèle différente de celle enregistrée), when l'analyse démarre, then le cas est `rejeté` avec la raison « modèle non vérifiable ».

### US-05 — Valider la prédiction (F-04)
En tant qu'opérateur, je veux que la prédiction soit validée par des règles explicites, afin de savoir si le résultat est exploitable.

- **AC-05.1** Given confiance ≥ seuil haut (défaut 0,70), qualité suffisante, cohérence non contradictoire, tous les artefacts présents et intègres, when la validation s'exécute, then le statut est « Accepté pour le prototype ».
- **AC-05.2** Given confiance < seuil haut ou qualité insuffisante ou cohérence contradictoire, when la validation s'exécute, then le statut est « Révision requise » avec la liste des règles non satisfaites.
- **AC-05.3** Given un artefact amont manquant ou dont l'empreinte recalculée diffère de l'empreinte ancrée, when la validation s'exécute, then le statut est « Rejeté » avec la raison « intégrité ».
- **AC-05.4** Given le résultat de validation, when il est affiché, then chaque règle apparaît avec son résultat (ok / échec / non applicable) et la valeur mesurée.

### US-06 — Recevoir explication et résultat final (F-05)
En tant qu'opérateur, je veux une explication simple et un résultat final, afin de comprendre la décision du prototype.

- **AC-06.1** Given une prédiction validée, when l'explication est générée, then elle cite la classe prédite, la confiance, les 2 classes suivantes et les règles de validation déterminantes, en ≤ 5 phrases.
- **AC-06.2** Given le statut de validation, when le résultat final est produit, then il contient la décision (Accepté / Révision requise / Rejeté), la mention « prototype — pas un diagnostic médical » et l'indication de révision éventuelle.

### US-07 — Hacher et ancrer chaque artefact (F-06, F-07, F-08)
En tant qu'auditeur, je veux que chaque artefact soit haché et ancré sur Fabric dès sa création, afin de disposer d'une preuve indépendante.

- **AC-07.1** Given un artefact produit (7 types : donnée originale, donnée traitée, caractéristiques, prédiction, validation, explication, résultat final), when il est stocké hors chaîne, then son SHA-256 est calculé sur sa forme canonique et une transaction Fabric enregistre : id artefact, id cas, type, empreinte, horodatage, version modèle/logiciel, id parent, référence hors chaîne, identité du composant émetteur.
- **AC-07.2** Given l'ancrage réussi, when l'opérateur ouvre le cas, then l'empreinte et l'identifiant de transaction de chaque artefact sont affichés.
- **AC-07.3** Given un identifiant d'artefact déjà ancré, when une seconde écriture est tentée, then le chaincode la refuse (pas d'écrasement).
- **AC-07.4** Given le réseau Fabric indisponible, when un ancrage échoue, then il est réessayé 3 fois puis le cas passe à `erreur_ancrage` ; aucun statut « Accepté » n'est émis.

### US-08 — Pipeline orchestré automatiquement (F-09)
En tant qu'opérateur, je veux que les étapes s'enchaînent sans intervention, afin d'obtenir le résultat de bout en bout.

- **AC-08.1** Given un cas créé, when le pipeline démarre, then les agents s'exécutent dans l'ordre préparation → caractéristiques → prédiction → validation → explication → résultat final, chacun déclenché par le succès du précédent.
- **AC-08.2** Given une étape en échec ou un statut « Rejeté », when l'orchestrateur reçoit le résultat, then il arrête les étapes dépendantes, produit un résultat final « Rejeté » motivé (ancré), et journalise la décision.
- **AC-08.3** Given chaque action d'agent, when elle se termine, then une entrée de journal (agent, étape, entrée, sortie, durée, statut) est enregistrée et consultable.

### US-09 — Consulter l'historique d'un cas (F-10)
En tant qu'auditeur, je veux voir la chaîne complète des artefacts d'un cas, afin de reconstituer comment le résultat a été obtenu.

- **AC-09.1** Given un cas terminé, when l'auditeur ouvre son historique, then les artefacts s'affichent dans l'ordre parent → enfant avec type, horodatage, empreinte, version, id de transaction, lus depuis Fabric.
- **AC-09.2** Given un identifiant de cas inexistant, when il est recherché, then le message « cas introuvable » s'affiche.

### US-10 — Vérifier l'intégrité (F-11)
En tant qu'auditeur, je veux recalculer les empreintes et les comparer à la blockchain, afin de détecter toute modification.

- **AC-10.1** Given un cas, when l'auditeur lance la vérification, then chaque artefact reçoit un statut : `valide` (empreinte identique), `modifié` (empreinte différente), `manquant` (fichier hors chaîne absent), `non_vérifiable` (aucun enregistrement Fabric ou Fabric injoignable).
- **AC-10.2** Given un fichier hors chaîne modifié d'un seul octet, when la vérification s'exécute, then cet artefact est `modifié` et les autres restent `valide`.
- **AC-10.3** Given une vérification, when elle se termine, then son résultat (date, auteur, statuts) est conservé et affiché.

### US-11 — Se connecter avec un rôle (F-13)
En tant qu'utilisateur, je veux me connecter, afin d'accéder aux fonctions de mon rôle uniquement.

- **AC-11.1** Given des identifiants valides, when l'utilisateur se connecte, then il accède au tableau de bord correspondant à son rôle.
- **AC-11.2** Given un auditeur, when il tente de créer un cas (UI ou API), then l'action est refusée (403).
- **AC-11.3** Given 5 échecs de connexion en 15 min, when une 6e tentative arrive, then le compte est temporairement bloqué 15 min.

### US-12 — Rejouer le scénario de démonstration (F-14)
En tant que membre de l'équipe, je veux un script et des cas de test d'intégrité, afin de démontrer de façon reproductible la détection de falsification.

- **AC-12.1** Given le système démarré, when le script de démo est lancé, then il crée un cas à partir d'un enregistrement PTB-XL fixé, attend le résultat final, modifie un artefact stocké et lance la vérification.
- **AC-12.2** Given la suite de tests d'intégrité, when elle s'exécute, then elle couvre au moins : tout valide, artefact modifié, artefact supprimé, enregistrement Fabric absent — et toutes passent.

### US-13 — Contrôle de cohérence ECG ↔ rapport (F-15, P0)
En tant qu'opérateur, je veux que la validation compare la prédiction aux termes du rapport, afin de repérer les contradictions.

- **AC-13.1** Given un rapport mentionnant un terme associé à une classe (ex. « infarctus » → MI), when la classe prédite est incompatible, then la règle de cohérence est « échec » et le statut devient « Révision requise ».
- **AC-13.2** Given un rapport sans terme reconnu, when la règle s'exécute, then elle est « non applicable ».

### US-14 — Voir une explication visuelle (F-16, P1 — non planifiée en v1, D-17)
En tant qu'opérateur, je veux voir les zones de l'ECG ayant le plus influencé la prédiction, afin de mieux comprendre le résultat.

- **AC-14.1** Given une prédiction, when l'opérateur ouvre l'explication, then le tracé ECG est affiché avec une surbrillance des segments les plus contributifs.

### US-15 — Recalculer les empreintes sur FPGA (F-18, P0)
En tant qu'auditeur, je veux qu'un module matériel indépendant recalcule les empreintes SHA-256, afin de confirmer celles du logiciel par une seconde implémentation.

- **AC-15.1** Given les vecteurs de test FIPS 180-4 (message vide, « abc », message de 448 bits, message de 896 bits), when ils sont hachés par le cœur VHDL en simulation, then chaque condensat est identique à la valeur de référence.
- **AC-15.2** Given 1 000 messages aléatoires de 0 à 4 096 octets, dont les longueurs limites 55, 56, 63, 64, 119 et 120 octets, when ils sont hachés en simulation, then 100 % des condensats sont identiques à ceux de `hashlib.sha256`.
- **AC-15.3** Given les 7 manifestes d'un cas de démonstration terminé, when ils sont hachés sur la carte Zybo Z7-10, then les 7 condensats sont identiques aux empreintes `sha256` lues sur Fabric.
- **AC-15.4** Edge : Given un manifeste modifié d'un octet, when il est haché sur la carte, then le condensat diffère de l'empreinte on-chain et le rapport indique « différent » pour cet artefact.

### US-16 — Filtrer l'ECG sur FPGA (F-19, P0)
En tant que membre de l'équipe, je veux que l'étage passe-bas + décimation du prétraitement ECG soit implémenté en VHDL, afin de démontrer une accélération matérielle bit-exacte du prétraitement.

- **AC-16.1** Given le gabarit du filtre (fe = 500 Hz ; bande passante 0–40 Hz avec ondulation ≤ 0,5 dB ; atténuation ≥ 40 dB à partir de 50 Hz ; décimation ×5), when les coefficients à virgule fixe sont générés, then la réponse fréquentielle calculée sur les coefficients quantifiés respecte le gabarit.
- **AC-16.2** Given des échantillons int16 aléatoires et les 12 dérivations de 5 enregistrements PTB-XL à 500 Hz, when ils traversent le bloc VHDL en simulation, then la sortie est identique bit à bit à celle du modèle de référence Python à virgule fixe.
- **AC-16.3** Given les 12 dérivations d'un cas de démonstration, when elles sont filtrées sur la carte Zybo Z7-10, then la sortie est identique bit à bit à l'étage correspondant enregistré dans l'artefact `processed` du cas.
- **AC-16.4** Edge : Given des entrées aux valeurs extrêmes (−32 768 et +32 767), when elles sont filtrées, then la sortie est saturée sans débordement, de façon identique au modèle de référence.

### US-17 — Co-vérifier et démontrer (F-20, P0)
En tant que membre de l'équipe, je veux un banc qui exporte les vecteurs d'un cas, les exécute en simulation ou sur la carte et produit un rapport, afin de prouver l'équivalence logiciel ↔ matériel et de la montrer en soutenance.

- **AC-17.1** Given un cas terminé, when la co-vérification est lancée avec la cible simulation ou carte, then un rapport (Markdown + JSON) liste chaque vecteur, la valeur attendue, la valeur obtenue et le verdict, ainsi que la version du bitstream et des coefficients.
- **AC-17.2** Given une modification sous `hw/` proposée en PR, when la CI s'exécute, then la co-vérification en simulation (AC-15.1, AC-15.2, AC-16.2) tourne et bloque la fusion en cas d'écart.
- **AC-17.3** Edge : Given la carte débranchée ou non programmée, when la cible carte est lancée, then le rapport indique « carte injoignable », le code de sortie est non nul et aucun verdict « identique » n'est émis.
- **AC-17.4** Given la soutenance, when l'étape 9 du scénario est jouée, then l'empreinte d'un artefact du cas de démonstration et le filtrage d'une dérivation sont recalculés en direct sur la carte et affichés comme identiques au registre et à l'artefact `processed` (D-13).

## 10. Exigences non fonctionnelles

Détaillées et numérotées (NFR-xx) dans le TRD. Résumé :

- **Performance :** pipeline complet ≤ 60 s par cas sur la machine de démo ; vérification d'un cas ≤ 10 s.
- **Fiabilité :** ancrage réessayé 3 fois ; aucun résultat « Accepté » sans ancrage complet.
- **Sécurité et confidentialité :** aucune donnée médicale brute ni identifiant direct sur la chaîne ; stockage hors chaîne chiffré ; accès authentifié par rôle ; transactions Fabric signées par l'identité du composant.
- **Traçabilité / reproductibilité :** chaque artefact référence son parent ; versions du modèle, du code et paramètres enregistrés.
- **Accessibilité :** interface lisible, contrastes WCAG AA, statuts non codés uniquement par la couleur.
- **Localisation :** interface en français.
- **Plateformes :** navigateur de bureau récent (Chrome, Firefox) ; déploiement Docker Compose sur une machine de démo ; carte Digilent Zybo Z7-10 (Zynq XC7Z010) pour le volet matériel.
- **Matériel :** résultats bit-exacts entre logiciel et VHDL ; contraintes de temps tenues à l'horloge cible ; build matériel reproductible par script.

## 11. Analytique et instrumentation

| Event | Trigger | Properties | Metric it feeds |
|---|---|---|---|
| `case_created` | Création d'un cas | case_id, user_role | Démonstration |
| `pipeline_completed` | Résultat final ancré | case_id, durée_totale, statut_final | Durée du pipeline |
| `artifact_anchored` | Transaction Fabric validée | case_id, artifact_type, tx_id | Couverture de traçabilité |
| `anchoring_failed` | Échec après réessais | case_id, artifact_type, erreur | Fiabilité |
| `integrity_check_completed` | Fin de vérification | case_id, nb_valide, nb_modifié, nb_manquant, nb_non_vérifiable | Taux de détection |
| `model_evaluated` | Script d'évaluation | model_version, auc_macro, f1_macro | Performance du modèle |
| `hw_coverification_completed` | Fin d'une co-vérification (rapport `hw/reports/`) | cible (sim/carte), nb_vecteurs, nb_identiques, version bitstream, version coefficients | Co-vérification logiciel ↔ matériel |

## 12. Contraintes

- **Délai :** soutenance le 2026-11-30 (D-16) ; développement du 2026-10-23 au 2026-11-30 après recalage (D-17) — aucun développement n'a eu lieu entre le 2026-10-05 et le 2026-10-23 (AAR-01).
- **Équipe :** 4 personnes.
- **Technique (imposé/choisi) :** Hyperledger Fabric (réseau de test), SHA-256, Python ; orchestration LangGraph ; données PTB-XL ; chaincode TypeScript ; VHDL sur Digilent Zybo Z7-10 (Zynq XC7Z010), outils AMD Vivado/Vitis 2023.x ou plus récent (déjà installé, D-12).
- **Répartition :** le volet VHDL est porté par le membre Ledger (cœurs, intégration Zynq, carte) avec le membre IA (coefficients du filtre et modèle de référence), sans renfort d'équipe (D-12).
- **Réglementaire :** données publiques PTB-XL (licence CC BY 4.0) ; aucune donnée patient réelle hors jeu public.
- **Budget :** aucun ; outils open source, exécution locale.

## 13. Hypothèses et dépendances

- **Hypothèses :**
  - Le « rapport médical » est le champ texte `report` de PTB-XL (majoritairement en allemand) ou un texte saisi en français par l'opérateur ; le contrôle de cohérence repose sur un lexique FR/DE/EN de mots-clés (D-08).
  - La tâche IA est la classification multi-étiquette des 5 superclasses diagnostiques PTB-XL sur les signaux 100 Hz.
  - Les étapes du pipeline sont déterministes ; LangGraph sert d'orchestrateur à états, sans LLM requis en P0.
  - Les « services autorisés » sont les agents, identifiés chacun par une identité Fabric (certificat MSP) distincte.
  - Une carte Zybo Z7-10 appartenant à l'équipe est disponible pendant tout le projet et le jour de la soutenance (D-14).
- **Dépendances :** jeu PTB-XL (PhysioNet), images Docker Hyperledger Fabric (fabric-samples test-network), bibliothèques Python (wfdb, PyTorch, LangGraph), AMD Vivado/Vitis, fichiers de carte Digilent, simulateur GHDL.

## 14. Risques et mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Mise en place de Fabric plus longue que prévu | Élevée | Élevé | Commencer en M1 sur `fabric-samples/test-network` ; un membre dédié |
| Performance du modèle insuffisante | Moyenne | Moyen | Modèle CNN 1D de référence connu sur PTB-XL ; repli sur un classifieur de caractéristiques (scikit-learn) |
| Sérialisation non canonique → faux « modifié » | Moyenne | Élevé | Règle de canonisation unique (TRD) + tests de stabilité du hachage |
| Machine de démo trop faible (Fabric + modèle) | Moyenne | Moyen | Inférence CPU, modèle léger ; répétition de la démo en M5–M6 |
| Fuite d'identifiants dans les métadonnées | Faible | Élevé | Pseudonymisation à l'entrée + test automatisé « rien d'identifiant on-chain » |
| Surcharge du membre Ledger (Fabric en M1–M2 puis VHDL en M3–M6) | Élevée | Élevé | Le membre IA fait coefficients et modèle de référence (M2) ; le membre Backend fait l'export et la simulation côté PC ; tâches non critiques coupables (Plan §2) |
| Écart logiciel ↔ matériel (arrondi, saturation, ordre des octets) | Moyenne | Élevé | Modèle de référence Python unique utilisé à la fois par le pipeline et les tests VHDL ; tests bit-exacts dès la simulation |
| Carte indisponible ou défaillante le jour J | Faible | Élevé | Image de démarrage sur carte SD, vidéo de secours de l'étape 9, rapport de co-vérification sur carte déjà produit en M4 (T4.14) |

## 15. Plan de livraison

| Milestone | Scope | Target date |
|---|---|---|
| Fondations | Réseau Fabric, chaincode minimal, squelette API, dataset prêt, chaîne VHDL (GHDL + Vivado) prête, coefficients FIR et modèle de référence | 2026-11-03 (M2) |
| Pipeline IA | Préparation, modèle entraîné, prédiction, validation ; cœurs SHA-256 et FIR validés en simulation | 2026-11-15 (M3) |
| Traçabilité de bout en bout | Hachage, stockage, ancrage, orchestration LangGraph ; intégration Zynq et co-vérification sur carte | 2026-11-20 (M4) |
| Démo et rapport | Interface, vérification, kit de démo, tests, étape matérielle, rapport final | 2026-11-30 (M6) |

- **Rollout :** démonstration locale via Docker Compose ; aucune mise en production.

## 16. Critères de lancement (soutenance)

- Toutes les stories P0 (US-01 à US-13, US-15 à US-17) passent leurs critères d'acceptation.
- Scénario de démonstration (CDC §9 + étape matérielle 9) exécuté de bout en bout sans intervention manuelle hors téléversement, modification volontaire et lancement de l'étape carte.
- Rapports de co-vérification en simulation et sur carte à 100 % identiques, versionnés dans `hw/reports/`.
- Suite de tests d'intégrité verte ; test « aucune donnée identifiante on-chain » vert.
- Les 10 livrables du CDC §12 sont présents dans le dépôt.

## 17. Communication et support

Rapport final court (implémentation et résultats, dont le volet matériel : architecture, ressources, timing, co-vérification), README d'installation, script de démo, diaporama de soutenance `[TBD: format exigé]`. Support : l'équipe pendant la soutenance.

## 18. Questions ouvertes

Suivies dans [review.md](review.md) (Q-01 et suivantes) avec propriétaire et échéance.

## Glossaire

| Terme | Définition |
|---|---|
| Cas | Une analyse : un ECG + un rapport optionnel, identifié par `CASE-<uuid>` |
| Artefact | Toute donnée produite ou reçue par le pipeline (7 types, voir US-07) |
| Empreinte | Hachage SHA-256 de la forme canonique d'un artefact |
| Ancrage | Enregistrement d'une empreinte et de ses métadonnées sur Fabric |
| Provenance | Chaîne parent → enfant des artefacts d'un cas |
| Statut de validation | Accepté (pour le prototype) / Révision requise / Rejeté |
| Statut d'intégrité | valide / modifié / manquant / non_vérifiable |
| Co-vérification | Exécution des mêmes vecteurs d'entrée par le logiciel et par le VHDL, avec comparaison bit à bit des sorties |
| Bit-exact | Sorties identiques à l'octet/au bit près (pas de tolérance) |
| FIR | Filtre à réponse impulsionnelle finie ; ici passe-bas 40 Hz suivi d'une décimation ×5 (500 → 100 Hz) |
| PS / PL | Parties du Zynq : processeur ARM (Processing System) / logique programmable FPGA (Programmable Logic) |
| Bitstream | Fichier de configuration de la logique programmable |

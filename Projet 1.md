# Système Agentique d'Analyse Médicale Sécurisée et Traçable par IA et Hyperledger Fabric

*Cahier des charges du mini-projet — Année universitaire 2026*

## Résumé du projet

Une donnée médicale (signal ECG et rapport associé) est analysée par un modèle d'intelligence artificielle, puis validée selon des règles simples. Chaque entrée et chaque résultat produit sont hachés, et leur empreinte ainsi que leur historique sont enregistrés sur Hyperledger Fabric, afin que toute modification ultérieure puisse être détectée. L'ensemble du processus est automatisé par un système agentique orchestrant les différentes étapes du pipeline.

# 1. Contexte du projet

Les systèmes d'IA médicale peuvent analyser des informations telles que des signaux ECG ou des rapports médicaux. Il reste toutefois difficile de prouver, a posteriori, quelles données, quelle méthode de prétraitement, quelle version de modèle et quel résultat de validation ont conduit à une décision donnée.

Ce mini-projet propose une solution simple combinant intelligence artificielle et blockchain : l'IA effectue l'analyse de la donnée médicale, tandis qu'Hyperledger Fabric constitue un registre permanent et traçable de l'historique de traitement. Il s'agit d'un prototype pédagogique, qui n'a pas vocation à remplacer un médecin ni à fournir un diagnostic médical autonome.

# 2. Objectif principal

Le système à construire doit être capable de :

* recevoir un fichier ECG et un rapport médical ;
* nettoyer et préparer la donnée médicale ;
* analyser la donnée préparée à l'aide d'un modèle d'IA ;
* valider la prédiction et son niveau de confiance ;
* générer un résultat final accompagné d'une explication simple ;
* calculer une empreinte cryptographique pour chaque entrée et sortie importante ;
* enregistrer ces empreintes et l'historique de traitement sur Hyperledger Fabric ; et
* vérifier si une donnée stockée a été modifiée après son traitement.

# 3. Flux de travail simplifié

Le processus global suit l'enchaînement suivant : réception de l'ECG et du rapport médical → nettoyage et préparation des données → analyse et prédiction par l'IA → validation de la prédiction → génération de l'explication et du résultat final → hachage et enregistrement sur Hyperledger Fabric.

Le hachage est réalisé à chaque étape importante et non uniquement à la fin. Le système conserve ainsi une empreinte des données brutes, des données traitées, des caractéristiques extraites, de la prédiction, du résultat de validation, de l'explication et du résultat final.

# 4. Composants du système

## 4.1 Entrée des données médicales

La première version du système accepte un signal ou fichier ECG ainsi qu'un rapport médical lié à l'examen. Les identifiants personnels sont supprimés ou remplacés par un identifiant de cas pseudonymisé avant l'entrée dans le pipeline de traitement.

## 4.2 Préparation des données

Le module de préparation vérifie et nettoie les données reçues. Selon le jeu de données retenu, la préparation de l'ECG peut inclure :

* la vérification du format du fichier ;
* la détection des valeurs manquantes ou invalides ;
* le débruitage du signal ;
* la normalisation des valeurs de l'ECG ;
* le découpage du signal en segments adaptés ; et
* la conversion du résultat au format requis par le modèle d'IA.

Le module produit une donnée traitée ainsi qu'un court rapport de traitement.

## 4.3 Module d'analyse IA

Le module d'IA reçoit les données ECG préparées et produit une prédiction. Un modèle de classification simple, entraîné au préalable, suffit pour le mini-projet ; un modèle plus avancé pourra être ajouté ultérieurement. L'artefact de prédiction contient la classe prédite, le score de confiance ou les probabilités par classe, le nom et la version du modèle, l'identifiant de la donnée d'entrée, ainsi que la date et l'heure de l'analyse.

## 4.4 Module de validation

Le module de validation vérifie la fiabilité de la prédiction à l'aide de règles simples fondées sur la confiance de l'IA, la qualité des données ECG, la cohérence entre le résultat ECG et le rapport disponible, la disponibilité de tous les artefacts requis et la vérification d'intégrité des étapes précédentes. Le résultat de validation peut être :

* Accepté pour le prototype : le résultat satisfait les contrôles configurés ;
* Révision requise : la confiance ou la qualité des données est insuffisante ; ou
* Rejeté : le pipeline est incomplet ou un problème d'intégrité est détecté.

## 4.5 Module de hachage

Chaque artefact important est converti en une représentation numérique cohérente puis haché avec SHA-256. Pour un artefact x, son empreinte est hx = SHA256(x). Lors d'une vérification ultérieure, le système recalcule le hachage : s'il diffère de la valeur enregistrée sur la blockchain, l'artefact stocké a été modifié ou ne correspond plus à l'original.

## 4.6 Module Hyperledger Fabric

Hyperledger Fabric stocke les empreintes et les informations de provenance ; les fichiers médicaux originaux restent dans un stockage hors chaîne protégé, du fait de leur taille et de leur sensibilité. Pour chaque artefact, l'enregistrement sur la blockchain contient : l'identifiant de l'artefact, l'identifiant de cas pseudonymisé, le type d'artefact, l'empreinte SHA-256, l'horodatage de création, la version du modèle ou du logiciel, l'identifiant de l'artefact parent, la référence de stockage hors chaîne, et l'identité du composant autorisé ayant créé l'enregistrement.

## 4.7 Orchestration par un système agentique

L'ensemble du processus — préparation des données, analyse IA, validation, génération de l'explication, hachage et enregistrement sur Hyperledger Fabric — est automatisé par un système agentique. Des agents autonomes spécialisés, coordonnés par un agent orchestrateur, prennent en charge chaque étape du pipeline sans intervention manuelle, déclenchent l'étape suivante selon le résultat de l'étape précédente, gèrent les cas d'erreur ou de rejet, et consignent leurs actions afin de préserver la traçabilité de bout en bout du processus.

# 5. Données générées durant le processus

Les artefacts forment une séquence traçable : Donnée originale → Donnée traitée → Caractéristiques → Prédiction → Validation → Résultat final. Chaque artefact référence son artefact parent, ce qui permet de reconstituer l'historique complet ayant conduit au résultat final.

| **Artefact** | **Description** |
| --- | --- |
| Donnée originale | ECG et rapport médical originaux reçus par le système. |
| Donnée traitée | Données nettoyées et normalisées, prêtes pour l'analyse. |
| Caractéristiques extraites | Valeurs ou représentation du signal utilisées par le modèle d'IA. |
| Prédiction IA | Classe prédite, probabilités, version du modèle et métadonnées associées. |
| Résultat de validation | Confiance, contrôles de qualité et de cohérence, statut de validation. |
| Explication | Information simple expliquant la prédiction ou le résultat de validation. |
| Résultat final | Décision finale du prototype et indication d'une éventuelle révision requise. |

# 6. Exigences fonctionnelles

Le prototype doit fournir les fonctions suivantes :

* Télécharger un ECG et un rapport médical.
* Attribuer un identifiant de cas pseudonymisé unique.
* Préparer la donnée médicale pour l'analyse.
* Exécuter le modèle d'IA sélectionné.
* Afficher la prédiction et le score de confiance.
* Valider la prédiction selon des règles prédéfinies.
* Stocker les artefacts générés dans un espace hors chaîne sécurisé.
* Calculer l'empreinte SHA-256 de chaque artefact.
* Enregistrer chaque empreinte et ses métadonnées sur Hyperledger Fabric.
* Afficher l'historique de traitement d'un cas sélectionné.
* Recalculer les empreintes pour vérifier l'intégrité des artefacts.
* Indiquer si un artefact est valide, modifié, manquant ou non vérifiable.

# 7. Exigences non fonctionnelles

* Sécurité : seuls les utilisateurs et services autorisés peuvent accéder aux données ou soumettre des transactions.
* Confidentialité : les données médicales brutes et les informations directement identifiantes ne sont pas stockées sur la blockchain.
* Traçabilité : chaque artefact généré est relié à son origine et à son étape de traitement.
* Intégrité : toute modification d'un artefact stocké doit être détectable par comparaison de hachage.
* Clarté : l'interface doit présenter simplement les prédictions, le statut de validation et les résultats de vérification.
* Modularité : les composants IA, validation, stockage et blockchain peuvent être modifiés indépendamment.
* Reproductibilité : les versions des modèles, des logiciels et les paramètres importants sont enregistrés.

# 8. Technologies proposées

| **Composant** | **Technologie envisageable** |
| --- | --- |
| IA et prétraitement | Python, NumPy, pandas, SciPy, scikit-learn, TensorFlow/PyTorch |
| Gestion des données ECG | Fichiers compatibles WFDB ou représentation CSV simple |
| Interface applicative | Flask ou FastAPI |
| Blockchain | Réseau de test Hyperledger Fabric |
| Smart contract | Chaincode JavaScript, TypeScript, Go ou Java |
| Stockage hors chaîne | Stockage local protégé, PostgreSQL ou objet chiffré |
| Hachage | SHA-256 |
| Interface utilisateur | Tableau de bord web simple |
| Déploiement | Conteneurs Docker |

Les choix technologiques définitifs pourront être adaptés selon le temps disponible, les équipements et les exigences du cours.

# 9. Démonstration attendue

La démonstration du mini-projet doit présenter le scénario suivant :

* L'utilisateur télécharge un ECG et un rapport.
* Le système prépare les données et exécute le modèle d'IA.
* Une prédiction et un score de confiance sont affichés.
* Le validateur produit un résultat d'acceptation, de révision ou de rejet.
* L'application affiche les empreintes et les identifiants de transaction blockchain.
* L'historique de traitement est présenté, de la donnée originale au résultat final.
* Un fichier stocké est volontairement modifié.
* La fonction de vérification recalcule son empreinte et détecte qu'elle ne correspond plus à l'enregistrement blockchain.

Cette démonstration illustre l'idée centrale du projet : la blockchain n'effectue pas l'analyse médicale, mais elle protège la traçabilité et l'intégrité du processus d'IA.

# 10. Portée et limites

Le mini-projet comprend un signal médical principal, un rapport, un modèle d'IA, un module de validation simple, un stockage hors chaîne, le hachage des artefacts et un petit réseau Hyperledger Fabric.

Cette première version ne vise pas à fournir un diagnostic cliniquement validé et ne prouve pas qu'une prédiction de l'IA est médicalement correcte. La blockchain prouve uniquement que la donnée vérifiée correspond à celle précédemment enregistrée par le système : une donnée d'origine incorrecte ou un modèle imprécis peuvent toujours produire un résultat erroné.

# 11. Extensions futures possibles

* Données EEG et IRM ;
* Modèles LSTM, ARIMA, Markov, transformeurs, ou autres ;
* Analyse multimodale combinant signaux, images et texte ;
* Estimation avancée de l'incertitude ;
* Méthodes d'IA explicable ;
* Validation du langage des rapports ou modèles vision-langage ;
* Revue clinique et approbation signée numériquement ; et
* Mécanismes renforcés de confidentialité et de contrôle d'accès.

# 12. Livrables attendus

À l'issue du mini-projet, les éléments suivants doivent être disponibles :

* le code source du pipeline de traitement des données médicales ;
* un modèle d'IA entraîné ou configuré ;
* un module de validation ;
* la configuration du réseau Hyperledger Fabric ;
* le chaincode d'enregistrement et de récupération des artefacts ;
* un stockage hors chaîne sécurisé des artefacts ;
* une fonction de vérification ;
* une interface de démonstration simple ;
* des cas de test illustrant des vérifications d'intégrité réussies et échouées ; et
* un rapport final court décrivant l'implémentation et les résultats.

# 13. Conclusion

Ce mini-projet montre comment l'intelligence artificielle et la blockchain peuvent se compléter dans un flux de traitement de données médicales. L'IA analyse l'ECG et le rapport associé, tandis qu'Hyperledger Fabric enregistre une preuve cryptographique de chaque étape importante du traitement. Le résultat est un prototype restreint mais complet, qui rend le processus d'IA plus facile à inspecter, à tracer et à vérifier.

*L'idée centrale peut se résumer ainsi : analyser la donnée médicale par IA, valider le résultat, hacher chaque artefact important, stocker les empreintes et la provenance sur Hyperledger Fabric, puis vérifier l'historique complet en cas de besoin.*
# SAAMSTIAHF — UI and UX Design Brief

| Owner | Reviewers | Status | Version | Last updated | Suite version | PRD | App Flow | TRD |
|---|---|---|---|---|---|---|---|---|
| Équipe projet | Encadrant `[TBD: nom, Q-12]` | In review | 2.0.1 | 2026-10-23 | 2.0.1 | [01-prd.md](01-prd.md) | [06-app-flow.md](06-app-flow.md) | [02-trd.md](02-trd.md) |

## 1. Objectifs de design et critères de succès

| Goal | Measure | Target |
|---|---|---|
| Le jury comprend le résultat d'un cas sans explication orale | Test « 5 secondes » sur S-04 : décision, classe et confiance citées correctement | 2/2 testeurs (hors équipe, D-17) |
| La preuve d'intégrité est lisible | Sur S-06, un testeur identifie l'artefact modifié et dit pourquoi | 2/2 testeurs, < 15 s |
| Le parcours principal est autonome | J-01 réalisé sans aide (S-02 → S-04 terminé) | 2/2 testeurs, < 2 min hors temps de traitement |
| Accessibilité | Audit axe DevTools sur S-01 à S-08, S-11, S-12 | 0 violation « serious » ou « critical » |

## 2. Public et contexte d'usage

- **Persona principal :** opérateur d'analyse (étudiant/ingénieur), à l'aise avec l'informatique, peu expert en cardiologie ou en blockchain.
- **Personas secondaires :** auditeur (cherche des preuves, lit des empreintes) ; jury (regarde un **vidéoprojecteur** à distance).
- **Contexte :** ordinateur portable 1366–1920 px, souris/clavier, salle éclairée, projection → contrastes élevés, texte ≥ 16 px, pas d'information en couleurs pâles seulement.
- **Adjectifs :**
  - **Clinique** → fonds blancs/gris très clairs, une seule couleur primaire sobre (bleu profond), aucune décoration ; tracé ECG sur grille papier rose classique.
  - **Vérifiable** → toute empreinte et tout tx_id en police monospace, copiables, avec icône chaîne violette « ancré » ; statuts toujours icône + libellé.
  - **Calme** → densité moyenne, espacements de 16–24 px, animations courtes et rares, aucune alerte rouge hors erreurs réelles.

## 3. Fondation de marque

- **Charte existante :** aucune.
- **Fixe :** nom du projet « SAAMSTIAHF » ; mention « Prototype pédagogique » visible.
- **Ouvert :** tout le reste (défini ici).
- **Logo :** logotype texte « SAAMSTIAHF » (Inter 700, 20 px) précédé d'une icône Lucide `heart-pulse` + `link` `[TBD: logo dessiné, Q-10]` ; marge libre ≥ 8 px ; uniquement sur fond `surface` ou `background`.

## 4. Voix et ton

- **Voix :** factuelle, précise, prudente sur le médical (jamais « diagnostic », toujours « résultat du prototype »), vouvoiement.

| Situation | Do | Don't |
|---|---|---|
| Bouton | Verbe d'action : « Lancer l'analyse », « Vérifier l'intégrité » | « OK », « Valider » ambigu |
| Erreur | Cause + action : « Taille maximale : 20 Mo. » | « Erreur 400 », jargon technique seul |
| État vide | Ce qui manque + prochaine action : « Aucun cas pour l'instant. » + bouton | Écran blanc |
| Résultat médical | « Résultat du prototype : MI (82 %) » | « Le patient a fait un infarctus » |
| Blockchain | « Ancré sur le registre (tx 3fa2…) » | « Sécurisé par la blockchain ! » |

- **Règles de contenu :** majuscule initiale uniquement ; dates `05/10/2026 14:32` (heure locale, UTC en infobulle) ; pourcentages sans décimale (`82 %`, espace insécable) ; probabilités brutes à 2 décimales dans les détails ; empreintes tronquées `3fa2b1c4…9e01` (8+4) avec copie de la valeur complète ; abréviations des classes avec libellé au survol (NORM = Normal, MI = Infarctus du myocarde, STTC = Anomalies ST/T, CD = Troubles de conduction, HYP = Hypertrophie).

## 5. Références

| Product / link | Screen or pattern | Borrow | Avoid |
|---|---|---|---|
| Explorateurs de blocs (ex. Etherscan) | Page de transaction | Champs hash/tx monospace + copie, statut clair | Densité extrême, publicité, jargon |
| Interfaces de CI (ex. pipelines GitHub Actions) | Frise d'étapes | Étapes avec statut et durée, journal dépliable | Couleurs vives multiples |
| Visionneuses ECG (papier 25 mm/s) | Tracé 12 dérivations | Grille rose millimétrée, disposition 3×4 + DII long | Fond noir « moniteur » (illisible en projection) |

- **Anti-références :** esthétique « crypto » (néons, dégradés, fonds sombres), tableaux de bord médicaux surchargés.

## 6. Design tokens

Exposés en variables CSS et mappés dans `tailwind.config.ts` (`theme.extend.colors`, `spacing`, `borderRadius`, `fontFamily`). Noms identiques dans le code et les maquettes.

```css
:root {
  --color-primary: #1E40AF; --color-primary-hover: #1E3A8A; --color-on-primary: #FFFFFF;
  --color-accent: #6D28D9; --color-accent-bg: #EDE9FE;
  --color-background: #F8FAFC; --color-surface: #FFFFFF;
  --color-text: #0F172A; --color-text-muted: #475569; --color-text-disabled: #94A3B8;
  --color-border: #E2E8F0; --color-border-strong: #64748B; --color-focus: #2563EB;
  --color-success: #15803D; --color-success-bg: #DCFCE7;
  --color-warning: #B45309; --color-warning-bg: #FEF3C7;
  --color-danger: #B91C1C;  --color-danger-bg: #FEE2E2;
  --color-info: #0369A1;    --color-info-bg: #E0F2FE;
  --ecg-trace: #111827; --ecg-grid-minor: #FDECEE; --ecg-grid-major: #F4B6C2; --ecg-saliency: #FDE68A;
  --font-sans: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, "Cascadia Code", Consolas, monospace;
  --radius-sm: 4px; --radius-md: 8px; --radius-lg: 12px;
  --shadow-1: 0 1px 2px rgba(15,23,42,.06), 0 1px 3px rgba(15,23,42,.10);
  --shadow-2: 0 10px 25px rgba(15,23,42,.15);
  --duration-fast: 120ms; --duration-base: 200ms; --ease: cubic-bezier(.2,0,0,1);
}
```

## 7. Couleur

| Token (role) | Light | Dark | Use |
|---|---|---|---|
| primary | #1E40AF | — | Boutons principaux, liens, onglet actif |
| primary-hover | #1E3A8A | — | Survol/pression des boutons principaux |
| accent | #6D28D9 | — | Éléments blockchain : icône « ancré », tx_id, frise de provenance |
| accent-bg | #EDE9FE | — | Fond des badges « Ancré » |
| background | #F8FAFC | — | Fond de page |
| surface | #FFFFFF | — | Cartes, tableaux, modales |
| text / text-muted | #0F172A / #475569 | — | Texte principal / secondaire |
| text-disabled | #94A3B8 | — | Texte désactivé (exempté WCAG) |
| border / border-strong | #E2E8F0 / #64748B | — | Séparateurs décoratifs / bordures de champs et contrôles |
| focus | #2563EB | — | Anneau de focus 2 px + décalage 2 px |
| success (+bg) | #15803D / #DCFCE7 | — | Accepté, Valide, étape ancrée |
| warning (+bg) | #B45309 / #FEF3C7 | — | Révision requise, Non vérifiable |
| danger (+bg) | #B91C1C / #FEE2E2 | — | Rejeté, Modifié, Manquant, erreurs |
| info (+bg) | #0369A1 / #E0F2FE | — | En cours, informations, mention prototype |

- **Mode sombre :** hors v1 (projection et démo en clair) — colonne « Dark » volontairement vide.
- **Nuances :** échelle Tailwind `blue`, `violet`, `slate`, `green`, `amber`, `red` ; seules les valeurs ci-dessus sont autorisées dans les composants.
- **Contrôles de contraste (calculés, formule WCAG 2.x) :**

| Pair | Ratio | AA |
|---|---|---|
| text / surface | 17,85:1 | ✓ |
| text / background | 17,06:1 | ✓ |
| text-muted / surface | 7,58:1 | ✓ |
| text-muted / background | 7,24:1 | ✓ |
| primary / surface (liens) | 8,72:1 | ✓ |
| on-primary / primary | 8,72:1 | ✓ |
| on-primary / primary-hover | 10,36:1 | ✓ |
| accent / surface | 7,10:1 | ✓ |
| accent / accent-bg | 5,98:1 | ✓ |
| success / surface ; success / success-bg | 5,02:1 ; 4,57:1 | ✓ ; ✓ (marge faible : ne pas éclaircir) |
| warning / surface ; warning / warning-bg | 5,02:1 ; 4,51:1 | ✓ ; ✓ (marge faible : ne pas éclaircir) |
| danger / surface ; danger / danger-bg ; blanc / danger | 6,47 ; 5,30 ; 6,47:1 | ✓ |
| info / surface ; info / info-bg | 5,93:1 ; 5,17:1 | ✓ |
| border-strong / surface (composant UI, ≥ 3:1) | 4,76:1 | ✓ |
| focus / surface (≥ 3:1) | 5,17:1 | ✓ |
| ecg-trace / ecg-grid-minor | 15,55:1 | ✓ |
| text / ecg-saliency | 14,33:1 | ✓ |

## 8. Typographie

- **Familles :** Inter (UI) et JetBrains Mono (empreintes, tx_id, identifiants de cas, valeurs numériques des règles) — toutes deux **SIL Open Font License 1.1**, auto-hébergées (pas d'appel Google Fonts en démo hors ligne).

| Level | Size | Line height | Weight | Use |
|---|---|---|---|---|
| Display | 32 px | 40 px | 700 | Décision sur S-04 (« Accepté pour le prototype ») |
| H1 | 24 px | 32 px | 600 | Titre d'écran |
| H2 | 20 px | 28 px | 600 | Titre de carte |
| H3 | 16 px | 24 px | 600 | Sous-section, en-têtes de tableau |
| Body | 16 px | 24 px | 400 | Texte courant |
| Small | 14 px | 20 px | 400 | Métadonnées, aide de champ, cellules denses |
| Mono | 14 px | 20 px | 400 | Empreintes, tx_id (`font-variant-numeric: tabular-nums`) |
| Caption | 12 px | 16 px | 500 | Légendes du tracé ECG uniquement |

- **Mise à l'échelle :** unités `rem` ; mise en page fonctionnelle jusqu'à 200 % de zoom navigateur.

## 9. Mise en page et espacements

- **Échelle :** 4 / 8 / 12 / 16 / 24 / 32 / 48 px.
- **Grille :** 12 colonnes, gouttière 24 px, marges 32 px.
- **Points de rupture :** 1280 px (cible, mise en page 2 colonnes sur S-04) ; < 1280 px : colonnes empilées. Pas de mise en page mobile (App Flow §1).
- **Largeur max du contenu :** 1440 px, centré.
- **Zones sûres :** sans objet (web desktop).

## 10. Élévation, rayons, bordures

- Niveau 0 : à plat (fond). Niveau 1 (`--shadow-1`) : cartes. Niveau 2 (`--shadow-2`) : modales, menus, toasts.
- Rayons : 4 px (badges, champs), 8 px (boutons, cartes), 12 px (modales).
- Bordures : 1 px `border` (séparateurs) ; 1 px `border-strong` (champs) ; 2 px `focus` (focus) ; 2 px `danger` (champ en erreur).

## 11. Iconographie

Lucide (ISC), contour, trait 2 px, tailles 16 / 20 / 24 px. Correspondances fixes : `check-circle-2` valide/accepté, `alert-triangle` révision/non vérifiable, `x-circle` rejeté/modifié, `file-x` manquant, `link` ancré, `loader-2` en cours, `copy` copier, `shield-check` vérifier l'intégrité, `upload` téléverser. Une icône seule (sans libellé) n'est permise que pour « copier », avec `aria-label` et infobulle.

## 12. Imagerie et illustration

Aucune photo ni illustration. Seul visuel : le tracé ECG (§18). États vides : icône Lucide 48 px `text-muted` + texte.

## 13. Mouvement

- 120 ms (survols, focus), 200 ms (modales, onglets, toasts), easing `--ease`.
- Animé : spinner de l'étape en cours, apparition de la coche « ancrée », toast.
- Non animé : changement de décision, tableaux, tracé ECG.
- `prefers-reduced-motion: reduce` → aucune transition ; spinner remplacé par le texte « en cours ».

## 14. Composants

Construits en React + Tailwind (TRD §4) ; primitives accessibles Radix UI (`@radix-ui/react-*`, MIT) pour modale, onglets, infobulle, menu.

| ID | Component | Variants | Sizes | States | Notes |
|---|---|---|---|---|---|
| C-button | Bouton | primary, secondary (contour), ghost, danger | md 40 px, sm 32 px | default, hover, focus, pressed, disabled, loading | Loading : spinner + libellé conservé, non cliquable |
| C-text-field | Champ texte / mot de passe / nombre | — | 40 px | default, focus, error, disabled, read-only | Libellé au-dessus, aide en dessous, erreur `danger` + icône |
| C-file-drop | Zone de dépôt de fichiers | ecg, rapport | — | vide, survol-glisser, fichiers choisis, erreur, envoi (barre %) | Liste des fichiers avec taille et bouton retirer |
| C-select | Liste déroulante / segmented (format WFDB/CSV) | — | 40 px | default, focus, disabled | — |
| C-textarea | Zone de texte du rapport | — | 6 lignes | default, focus, error, compteur 0/10 000 | — |
| C-card | Carte | default, highlighted (décision) | — | default, loading (squelette) | Titre H2, contenu, pied optionnel |
| C-top-nav | Barre supérieure | — | 56 px | lien actif souligné 2 px primary | Menu admin visible pour admin seulement |
| C-tabs | Onglets S-04…S-07 | — | 44 px | default, hover, focus, selected | Liens d'URL (App Flow §11) |
| C-banner | Bandeau | info, success, warning, danger | — | — | Icône + texte + action optionnelle |
| C-toast | Notification | success, danger | — | apparition 200 ms, fermeture 5 s ou bouton | `role="status"` |
| C-modal | Modale / confirmation | default, destructive | 480 / 640 px | ouverte, envoi | Focus piégé, Échap ferme |
| C-table | Tableau | default, compact | lignes 48 / 40 px | survol de ligne, ligne dépliable, tri, vide, chargement | Pagination (S-02) |
| C-status-badge | Badge de statut | decision (3), integrity (4), case_status (5), anchor (3) | 24 px | — | Icône + libellé obligatoires ; couleurs §7 |
| C-hash | Empreinte / tx_id | hash, tx, case_ref | — | default, hover (valeur complète en infobulle), copied (« Copié » 2 s) | Mono, tronquée 8…4, bouton copier |
| C-pipeline-stepper | Frise des 7 étapes | horizontale | — | à venir, en cours, ancrée, échec, non exécutée | `aria-live` pour les changements |
| C-provenance-timeline | Frise verticale de provenance | — | — | nœud default, nœud sélectionné | Lien parent → enfant, couleur accent |
| C-probability-bars | Barres des 5 probabilités | — | — | top classe surlignée | Valeurs texte à droite |
| C-rule-list | Résultats R1–R5 | — | — | ok, échec, non applicable | Valeur mesurée + seuil |
| C-ecg-viewer | Tracé ECG 12 dérivations | standard (variante saillance F-16 non planifiée, D-17) | 3×4 + DII long | chargement, erreur, zoom | Plotly, grille papier (§18) |
| C-empty-state | État vide | — | — | — | Icône 48 px + texte + action |
| C-skeleton | Squelette | ligne, carte, tableau | — | animation pulse (désactivée en reduced-motion) | Affiché après 300 ms seulement |
| C-tooltip | Infobulle | — | — | — | Clavier : au focus |

Hors périmètre v1 : sélecteur de date, avatar, bottom sheet.

## 15. États d'interaction

| State | Visual treatment | Notes |
|---|---|---|
| Default / hover / focus / pressed | hover : `primary-hover` ou fond `background` ; focus : anneau 2 px `focus` + décalage 2 px ; pressed : translation 1 px | Focus toujours visible (`:focus-visible`) |
| Selected / disabled / read-only | selected : soulignement/fond `accent-bg` ou `primary` ; disabled : opacité de texte `text-disabled`, curseur interdit ; read-only : fond `background`, pas de bordure forte | — |
| Loading / skeleton | spinner seulement après 300 ms ; squelettes pour les chargements de page | Bouton conserve sa largeur |
| Error / success | bordure + icône + texte ; toasts | Jamais la couleur seule |

## 16. Conventions de plateforme

Web desktop uniquement. Navigation du navigateur respectée (URLs, Précédent, Ctrl+clic sur les liens de cas). Raccourci `Ctrl+C` sur une empreinte sélectionnée.

## 17. Localisation

Français uniquement (NFR-10). Format `fr-FR` (`Intl.DateTimeFormat`, `Intl.NumberFormat`). Aucune langue RTL. Les rapports PTB-XL en allemand sont affichés tels quels, avec la mention « Langue d'origine du rapport ».

## 18. Visualisation de données

- **Tracé ECG (C-ecg-viewer) :** disposition 3×4 (I, II, III / aVR, aVL, aVF / V1–V3 / V4–V6) + DII long ; 25 mm/s, 10 mm/mV ; grille mineure 1 mm `ecg-grid-minor`, majeure 5 mm `ecg-grid-major` ; trait 1,25 px `ecg-trace` ; étiquette de dérivation en caption ; signal décimé côté API (`/signal`).
- **Saillance (P1, non planifiée en v1, D-17 ; spécification conservée) :** bandes verticales `ecg-saliency` (opacité 60 %) derrière le tracé + liste textuelle des segments (dérivation, intervalle en s).
- **Probabilités :** barres horizontales, une seule teinte `primary` (classe principale), autres `border-strong` ; ligne verticale pointillée au seuil `conf_high` ; valeur en % à droite. Pas de palette catégorielle (les classes ne sont pas comparées entre elles visuellement).

## 19. Notes par écran

### S-01 — Connexion
- **Action principale :** Se connecter. **Hiérarchie :** logotype → formulaire (e-mail, mot de passe) → bouton → « Mot de passe oublié ? Contactez un administrateur ». Carte centrée 400 px. Mention « Prototype pédagogique » en pied.

### S-02 — Liste des cas
- **Action principale :** Nouveau cas (operator/admin). **Hiérarchie :** titre + bouton → filtres (statut, décision) → tableau (case_ref mono, date, statut, classe, confiance, décision). **Vide :** C-empty-state. **Max :** pagination 20/page.

### S-03 — Nouveau cas
- **Action principale :** Lancer l'analyse. **Hiérarchie :** format (segmented) → dépôt ECG → fréquence (si CSV) → rapport (fichier ou texte) → bouton. Une colonne 640 px. Aide « Les identifiants personnels seront supprimés avant traitement » en `info`.

### S-04 — Cas · Résultat
- **Action principale :** lire la décision ; secondaire : Vérifier l'intégrité (lien vers S-06). **Hiérarchie :** en-tête (case_ref, date, statut) → **bandeau de décision** (Display, couleur + icône) + mention prototype → colonne gauche (8/12) : C-ecg-viewer ; colonne droite (4/12) : Prédiction, Validation, Explication → pleine largeur : tableau de traçabilité (7 lignes, C-hash, badge « Ancré »). **Au-dessus de la ligne de flottaison (1080 p) :** décision, classe + confiance. **En cours :** C-pipeline-stepper à la place du bandeau ; cartes en squelette.

### S-05 — Cas · Provenance
- **Action principale :** inspecter un nœud. **Hiérarchie :** frise verticale (7 nœuds, original en haut) → panneau de détail du nœud sélectionné (tous les champs on-chain). **Erreur registre :** C-banner danger + Réessayer.

### S-06 — Cas · Intégrité
- **Action principale :** Vérifier l'intégrité (C-button primary, icône `shield-check`). **Hiérarchie :** bouton + résumé de la dernière vérification → tableau des 7 statuts (empreinte on-chain vs recalculée, différence surlignée `danger-bg`) → historique des vérifications. **Démo :** la ligne « Modifié » doit être identifiable depuis le fond de la salle (badge + fond de ligne `danger-bg`).

### S-07 — Cas · Journal des agents
- **Action principale :** déplier une entrée. **Hiérarchie :** tableau chronologique ; durée totale en en-tête.

### S-08 — Admin · Utilisateurs
- **Action principale :** Nouvel utilisateur. Tableau (nom, e-mail, rôle, actif, dernière connexion) ; actions par ligne : Modifier, Désactiver/Réactiver.

### ~~S-09, S-10~~ — retirés v2.0.0 (D-17)
- Remplacés par `scripts/registry.py` (App Flow §10) ; sortie console selon les règles de la section « Sortie console de l'étape matérielle » ci-dessous.

### S-11 — Erreur 403 / 404
- **Action principale :** Retour à la liste des cas. Icône 48 px + titre H1 + phrase explicative.

### Hors application — Sortie console de l'étape matérielle (J-10, J-11)
- Pas d'écran web (D-11). Terminal projeté à côté de S-05 : thème clair, police JetBrains Mono ≥ 18 px, largeur ≥ 100 colonnes.
- Empreintes affichées en entier, l'une sous l'autre (« carte » puis « registre ») pour comparaison visuelle ; verdict final sur une ligne séparée : `✔ IDENTIQUE` en vert (`success`) ou `✖ DIFFÉRENT` en rouge (`danger`) — symbole + mot, jamais la couleur seule ; sortie lisible aussi sans couleur (`NO_COLOR`).
- En-tête : VERSION du bitstream et COEF_ID lus sur la carte.

### S-12 — À propos
- **Action principale :** aucune (lecture). Avertissement prototype, attribution PTB-XL (CC BY 4.0, citation), versions logiciel/modèle, liste des technologies.

## 20. Accessibilité

- **Cible :** WCAG 2.2 AA (NFR-09).
- **Contraste :** §7 (tous les couples validés).
- **Clavier et focus :** tout atteignable au clavier ; ordre logique (§19) ; lien « Aller au contenu » ; focus piégé dans les modales.
- **Lecteur d'écran :** libellés explicites (« Copier l'empreinte de l'artefact prédiction ») ; tableaux avec `<th scope>` ; progression en `aria-live="polite"` ; tracé ECG avec `aria-label` résumé + tableau de mesures alternatif.
- **Cibles :** ≥ 24×24 px (WCAG 2.2 2.5.8) ; boutons 40 px de haut.
- **Jamais la couleur seule :** C-status-badge impose icône + libellé.
- **Zoom et mouvement :** 200 % sans perte ; `prefers-reduced-motion` respecté (§13).

## 21. Ressources nécessaires

| Asset | Format / sizes | Owner | Due |
|---|---|---|---|
| Logo / logotype | SVG | `[TBD: membre front]` | 2026-11-13 (M3) |
| Icône d'application | Sans objet (web) | — | — |
| Écran de démarrage | Sans objet | — | — |
| Icônes | Lucide (package npm) | membre front | 2026-10-30 (M1–M2) |
| Illustrations | Aucune | — | — |
| Captures magasin | Sans objet | — | — |
| Favicon | SVG + ICO 32 px | membre front | 2026-11-13 (M3) |
| Polices Inter, JetBrains Mono | WOFF2 auto-hébergées | membre front | 2026-10-30 (M1–M2) |

## 22. Outils et remise

- **Outil :** Figma (gratuit, éducation) `[assumes D-pending Q-10]` — pages : Tokens, Composants (noms `C-*`), Écrans (noms `S-*`). Si pas de Figma : maquettes directement en code (Storybook optionnel).
- **Remise :** noms de composants identiques dans le code ; le membre front répond aux questions.

## 23. Validation

- **Tests d'utilisabilité :** M5 (≤ 2026-11-25), 2 testeurs hors équipe (réduit par D-17), 3 tâches (§1) ; critères §1.
- **Contrôle design :** revue croisée de chaque écran contre ce brief avant merge ; écart toléré : ± 4 px.

## 24. Calendrier et livrables

| Deliverable | Due |
|---|---|
| Tokens + composants de base (C-button, C-text-field, C-card, C-status-badge, C-hash) | 2026-10-30 (M1–M2) |
| Maquettes basse fidélité S-01 à S-08, S-11, S-12 | 2026-10-30 (M1–M2) |
| Écrans haute fidélité (en code) S-02 à S-06 | 2026-11-13 (M3) |
| C-ecg-viewer, C-pipeline-stepper, C-provenance-timeline | 2026-11-15 (M3) |
| Écrans restants + passe accessibilité | 2026-11-24 (M5) |

## 25. Contraintes

8 semaines, 4 personnes, aucun budget ; polices et icônes sous licences libres (OFL, ISC, MIT) ; démo hors ligne possible (aucun CDN).

## 26. Hypothèses

- La démo est projetée en mode clair ; le mode sombre n'apporte rien en v1.
- Plotly.js rend 12 dérivations × 1 000 points sans latence perceptible.

## 27. Questions ouvertes

Voir [review.md](review.md).

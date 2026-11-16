# SAAMSTIAHF — Matrice de traçabilité

Suite version : 2.1.4 — 2026-11-09. Une ligne par story. Statuts : drafted → reviewed → ready → in build → done. Composants (SVC), interfaces (IF) : Architecture ; flux (DF), modes de défaillance (FM) : System Design.

| Feature | Story | Priority | Acceptance criteria | Screens | Entities | Components | Flows | APIs / NFRs | UI components | Tasks | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F-01 | US-01 | P0 | AC-01.1, AC-01.2, AC-01.3 | S-03, S-04 | E-cases, E-jobs, E-audit_events | SVC-web, SVC-api, SVC-cases, SVC-audit | DF-01 | POST /cases ; NFR-05 ; FM-11 | C-file-drop, C-select, C-textarea, C-button | T3.4, T3.15 | ready |
| F-01 | US-02 | P0 | AC-02.1, AC-02.2, AC-02.3 | S-03 | E-cases (case_ref), E-artifacts (original), E-artifact_files | SVC-pipeline (ingestion), SVC-traceability | DF-01 | POST /cases ; NFR-03 | C-banner (info) | T3.6 | in build |
| F-02 | US-03 | P0 | AC-03.1, AC-03.2, AC-03.3 | S-04 | E-artifacts (processed : fir_input, fir_stage, signal), E-cases.quality_score | SVC-pipeline (preparation), SVC-dsp | DF-01 | IF-06 ; NFR-07, NFR-21 ; ADR-14 | C-pipeline-stepper | T2.10, T2.12, T3.7 | ready |
| F-03 | US-04 | P0 | AC-04.1, AC-04.2, AC-04.3 | S-04 | E-artifacts (features, prediction), E-models, E-ledger_model | SVC-pipeline (features, prediction), SVC-registry, SVC-ledger-client | DF-01, DF-03 | GET /cases/{id} ; GetModel ; IF-12 ; NFR-07 ; FM-10 | C-probability-bars, C-card | T2.5b, T3.8a, T3.8b, T3.9, T3.10, T3.16a, T4.7 | ready |
| F-04 | US-05 | P0 | AC-05.1, AC-05.2, AC-05.3, AC-05.4 | S-04 | E-artifacts (validation), E-validation_configs | SVC-pipeline (validation), SVC-registry, SVC-verification | DF-01 | `scripts/registry.py` (IF-12) ; IF-08 ; NFR-08 | C-rule-list, C-status-badge | T3.11, T3.16a, T4.7 | ready |
| F-05 | US-06 | P0 | AC-06.1, AC-06.2 | S-04 | E-artifacts (explanation, final_result), E-cases.decision | SVC-pipeline (explanation, finalization) | DF-01, DF-03 | GET /cases/{id} | C-card, C-banner | T3.12, T3.16a | ready |
| F-06, F-07, F-08 | US-07 | P0 | AC-07.1, AC-07.2, AC-07.3, AC-07.4 | S-04 | E-artifacts, E-artifact_files, E-ledger_artifact | SVC-traceability, SVC-hashing, SVC-ledger-client, SVC-ledger-gateway, SVC-chaincode | DF-01 | IF-04, IF-07, IF-09, IF-10 ; CreateArtifactRecord ; NFR-03, NFR-04, NFR-06, NFR-11, NFR-12 ; FM-01, FM-13 | C-hash, C-status-badge | T2.5a, T2.6, T2.7, T3.1, T3.2, T3.3, T3.16a, T3.17 | ready |
| F-09 | US-08 | P0 | AC-08.1, AC-08.2, AC-08.3 | S-04, S-07 | E-jobs, E-agent_logs | SVC-pipeline, SVC-cases | DF-01 | IF-02, IF-03 ; GET /cases/{id}/agent-logs ; NFR-01, NFR-14 ; FM-05 | C-pipeline-stepper, C-table | T3.5, T4.5, T5.9 | ready |
| F-10 | US-09 | P0 | AC-09.1, AC-09.2 | S-05 | E-ledger_artifact | SVC-api, SVC-ledger-client, SVC-chaincode | DF-04 | GET /cases/{id}/history ; GetCaseHistory ; FM-03 | C-provenance-timeline, C-hash | T4.2, T4.3 | ready |
| F-11 | US-10 | P0 | AC-10.1, AC-10.2, AC-10.3 | S-06 | E-verifications, E-verification_items | SVC-verification, SVC-traceability, SVC-ledger-client | DF-02 | POST/GET /cases/{id}/verifications ; IF-08 ; NFR-02, NFR-08 ; FM-02, FM-08 | C-table, C-status-badge, C-hash | T4.1, T4.4, T5.1 | ready |
| F-12, F-13 | US-11 | P0 | AC-11.1, AC-11.2, AC-11.3 | S-01, S-08, S-11 | E-users, E-refresh_tokens, E-login_attempts | SVC-web, SVC-api, SVC-identity | DF-07 | /auth/* ; /admin/users ; IF-11 ; NFR-05 ; FM-12 | C-text-field, C-button, C-modal | T2.3, T2.4, T2.8, T4.6 | ready |
| F-14 | US-12 | P0 | AC-12.1, AC-12.2 | S-04, S-06 | E-artifact_files, E-verifications | SVC-verification, SVC-traceability | DF-01, DF-02 | `scripts/demo.py`, `tamper.py` ; NFR-08 | — | T4.8, T5.1 | ready |
| F-15 | US-13 | P0 | AC-13.1, AC-13.2 | S-04 | E-artifacts (validation, original/report), E-validation_configs.lexicon_version | SVC-pipeline (validation), SVC-registry | DF-01 | — | C-rule-list | T3.11 | ready |
| F-16 | US-14 | P1 | AC-14.1 | — | — | — | — | — | — | Non planifiée en v1 (D-17) ; T4.10 retirée | reporté (D-17) |
| F-17 | — | P2 | — | — | — | — | — | drapeau `LLM_EXPLANATION_ENABLED` | — | non planifié | drafted |
| F-18 | US-15 | P0 | AC-15.1, AC-15.2, AC-15.3, AC-15.4 | — (CLI J-10, J-11) | E-artifacts (manifestes), E-ledger_artifact | SVC-hw-sha256, SVC-ps-app, SVC-hw-host, SVC-hashing, SVC-ledger-client | DF-05, DF-06 | IF-14, IF-15 ; NFR-16, NFR-17, NFR-18, NFR-19 ; FM-14, FM-15, FM-17 ; ADR-12, ADR-13 | — (sortie console DB) | T1.9, T3.18, T3.20, T3.21, T4.12, T4.14, T5.8 | ready |
| F-19 | US-16 | P0 | AC-16.1, AC-16.2, AC-16.3, AC-16.4 | — (CLI J-10, J-11) | E-artifacts (processed : fir_input, fir_stage) | SVC-hw-fir, SVC-ps-app, SVC-dsp, SVC-hw-host | DF-05, DF-06 | IF-06, IF-14, IF-16 ; NFR-16 à NFR-19, NFR-21 ; FM-16, FM-17 ; ADR-14 | — | T2.10, T2.11, T3.19, T3.20, T3.21, T4.12, T4.14, T5.8 | ready |
| F-20 | US-17 | P0 | AC-17.1, AC-17.2, AC-17.3, AC-17.4 | — (CLI J-10, J-11 ; à côté de S-05 en démo) | E-artifact_files (export admin) | SVC-hw-host, SVC-traceability, SVC-ledger-client | DF-05, DF-06 | `export_hw_vectors.py`, `coverify.py`, `demo_step.py` ; job CI `hw-sim` ; NFR-20 ; FM-14, FM-15, FM-16 ; ADR-16 | — (sortie console DB) | T1.10, T3.22, T4.13, T5.8, T6.3, T6.5 | ready |

## Éléments sans story (justifiés par une NFR, une contrainte ou un risque)

| Élément | Justification |
|---|---|
| S-12 À propos, T4.9 | Attribution PTB-XL CC BY 4.0 (TRD §13), mention prototype (PRD §7), `/health` (NFR-11) |
| E-audit_events, SVC-audit, T4.11 | PRD §11 (instrumentation) |
| T1.11 contrôles d'architecture | NFR-13, ADR-15, ADR-16 |
| T2.9 test « rien d'identifiant on-chain » | NFR-03 |
| T5.3 audit accessibilité et textes | NFR-09, NFR-10 |
| T5.4 banc de charge | NFR-01, NFR-02, NFR-15, NFR-20 (System Design §14) |
| T5.7 sauvegarde, restauration, purge | TRD §14 (RPO, RTO), System Design §12, Schema §16 |
| T5.9 injection de pannes, `reanchor.py`, `requeue.py` | NFR-11 ; FM-01, FM-04, FM-05, FM-06 (System Design §14) |
| T1.x mise en place, spikes | Risques PRD §14, TRD §22, System Design §18 |
| C-ecg-viewer (sans saillance), T3.16b | AC-04.2 (contexte de la prédiction), CDC §9 |
| FM-18, FM-19, FM-20 | Pannes sans écran applicatif (navigateur, PhysioNet, audit) : comportement documenté, pas de tâche dédiée |
| T2.1, T2.2 | Migration initiale et seed : socle des entités, préalable à tout cas (Schema §18) |
| S-02, T3.13, T3.14 | Liste et lecture des cas : écran d'entrée de la navigation (App Flow §5) ; le TRD §8.1 rattache `GET /cases` à US-09 |
| T5.2 | Tests E2E des parcours J-01, J-02 et J-04 (Plan T5.2) |
| T5.5 | Revue de sécurité : OWASP, secrets, privilèges (TRD §12, NFR-03, NFR-05) |
| T5.6 | Tests d'utilisabilité à 2 testeurs (Design Brief §1 et §23, D-17) |
| T6.1, T6.2, T6.4 | Livraison : machine de démo hors ligne, rapport final, tag `v1.0.0` (CDC §12, PRD §16 et §17, D-13) |

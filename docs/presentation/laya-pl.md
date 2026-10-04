---
marp: true
theme: laya
size: 16:9
lang: pl
paginate: true
header: LAYA SEC LAYER / AGENTGATE
footer: 2026-10-04 · Lokalny prototyp
---
<!-- _class: lead -->
<div class="kicker">AI Control Layer / HackYeah</div>

# Laya Sec Layer

**Kto działa, na jakich danych, z jakim skutkiem i zużyciem zasobów.**

Agent HR pracuje w nadanym zakresie. Człowiek sprawdza dokładną propozycję wiadomości przed jej wykonaniem.

<div class="note">AgentGate kontroluje wywołania modelu i rzeczywiste działania narzędzi.</div>

---
<!-- _class: compact -->
## HR: dane, podsumowanie, zgoda

<div class="columns"><div><div class="node"><strong>Alex Rivera · osoba fikcyjna</strong>Kandydat na koordynatora operacji.<br>3 lata układania grafików wsparcia.<br>Raporty w arkuszach i komunikacja.<br>Dostępność: przyszły miesiąc.</div><p class="note">Syntetyczny rekord i testowe CV. Bez rankingu kandydatów i decyzji o zatrudnieniu.</p></div><div><h3>Praca z kontrolowanym zakresem</h3><p>Pracownik HR wiąże agenta ze swoim zakresem. Agent czyta dostępny rekord. Podsumowanie wymaga wydania źródła przez bramę.</p><p>Człowiek przegląda odbiorcę, temat i treść. Wznowienie po zgodzie zapisuje jedną wiadomość w lokalnej skrzynce testowej.</p></div></div>

<div class="warn">Korzyść: pomoc w przygotowaniu materiału, widoczny zakres danych i kontrola nad konkretnym działaniem.</div>

<!-- Sources: accepted docs/hr-workflow.md at a370134, reviewed c9c47b8 (runtime 34bf344); synthetic fixture hr-candidate-001 in src/agentgate/documents.py. Summary uses the configured provider and inspected tool result, with no substitute response. -->

---
<!-- _class: compact architecture -->
## Dwie bramy, jedna polityka

<div class="flow"><div class="node"><strong>Agent / aplikacja</strong>Poświadczenie agenta<br>Żądanie do modelu</div><div class="arrow">→</div><div class="node"><strong>Brama LLM</strong>Wejście i wyjście<br>Alias modelu, limity</div><div class="arrow">→</div><div class="node"><strong>Prywatna trasa</strong>LiteLLM → Ollama<br>Pełny wynik przed wydaniem</div></div>
<div class="shared"><strong>Wspólna tożsamość, polityka, zgody, budżet i audyt</strong></div>
<div class="flow"><div class="node"><strong>Propozycja narzędzia</strong>REST / oficjalny MCP<br>Jawne aliasy operacji</div><div class="arrow">→</div><div class="node"><strong>Brama działań</strong>Zakres danych<br>Ponowna weryfikacja</div><div class="arrow">→</div><div class="node"><strong>Lokalny wykonawca</strong>Dokumenty i pamięć<br>Testowy outbox SQLite</div></div>
<div class="target-row"><div class="node"><strong>Usługi lokalne</strong>Laya / CoreML (opcjonalnie), audyt, kolektor.</div><div class="node proposed"><strong>Integracje zewnętrzne</strong>Firmowy IAM / SIEM/SOC: osobna akceptacja.</div></div>

<!-- Sources: docs/architecture.md, docs/model-gateway.md, docs/scoped-tools.md, docs/telemetry-delivery.md. Solid green boxes are local code paths; dashed orange box marks external deployment targets. Private route requires a trusted host and separately protected upstream access. -->

---
<!-- _class: compact -->
## Człowiek i agent: część wspólna

<div class="intersection"><div class="node"><strong>Pracownik HR</strong>Kandydat + CV<br>Prywatne notatki HR</div><div class="arrow">∩</div><div class="node"><strong>Agent HR</strong>Kandydat + CV<br>Rekord Finance</div><div class="arrow">=</div><div class="node result"><strong>Dozwolony odczyt</strong>Kandydat + CV<br>Globalna polityka nadal obowiązuje</div></div>

**Ten sam tenant nie oznacza dostępu do wszystkich jego danych.**

<div class="columns"><div><h3>Zaufane pochodzenie osoby</h3><p>Lokalny rekord operatora lub opcjonalna wymiana tokenu od przypiętego wystawcy. Weryfikacja podpisu nie nadaje dodatkowych uprawnień.</p></div><div><h3>Delegacja do 300 sekund</h3><p>Aktualny zakres i pierwotny limit nadal ograniczają agenta. Nowa osoba lub delegacja zachowuje właściciela rozliczeń i budżet głównego przebiegu.</p></div></div>

<div class="note">Wymiana tokenu: testy z wygenerowanymi kluczami. Konsola bez logowania ufa komputerowi i nie potwierdza tożsamości pracownika firmy.</div>

<!-- Sources: docs/delegated-authority.md; accepted docs/hr-workflow.md and docs/issuer-exchange.md. Human requester, approval actor and immutable accounting principal are separate. HR browser binding uses local_demo and session-private handles, never a browser-held agent bearer. -->

---
<!-- _class: compact -->
## Katalog narzędzi i dokładna zgoda

| Klasa i rzeczywisty adapter | Heurystyka 0–100 | Warunek działania |
|---|---:|---|
| Odczyt: dokumenty / pamięć | 25 | Zakres osoby i agenta, klasy danych |
| Zapis: lokalny outbox | 75 | Dozwolony odbiorca i dokładna zgoda |
| Destrukcyjne / nieznane | Brak adaptera | Odmowa przed wykonaniem |

<div class="note">Suma: efekt + możliwe dane + ekspozycja + odwracalność + wpływ na osobę. Lokalna heurystyka polityki, bez prawdopodobieństwa i klasyfikacji prawnej.</div>

<div class="flow"><div class="node"><strong>Propozycja</strong>Odbiorca, temat, treść<br>Stały klucz</div><div class="arrow">→</div><div class="node"><strong>Dokładna zgoda</strong>Niezmienna migawka<br>Bez efektu</div><div class="arrow">→</div><div class="node"><strong>Wznowienie</strong>Aktualne uprawnienia<br>Jeden wpis, bez duplikatu</div></div>

<div class="warn">Zmiana treści lub uprawnień wymaga nowej zgody. Lokalny outbox bez SMTP.</div>

<!-- Sources: docs/tool-catalog.md (tool-policy-heuristic-v1, scores 25 and 75); docs/scoped-tools.md; docs/delegated-authority.md. Components for mail: 25+25+10+5+10. Read: 0+25+0+0+0. Local_record_retained is a reversibility descriptor, not a recall guarantee. Hard denials remain mandatory at every score. -->

---
<!-- _class: compact taxonomy -->
## L0–L5 i siedem warstw ochrony

| Typ autorskiego scenariusza | Wąska ochrona / jawna granica |
|---|---|
| L0 · Przypadek | Wzorce tekstu i budżety / brak ogólnego DLP |
| L1 · Bezpośrednia znana próba | Uprawnienia i rejestr / brak uniwersalnego detektora |
| L2 · Ukrywanie i omijanie | Ścisły rejestr operacji / brak ogólnej normalizacji |
| L3 · Treść pośrednia | Zakres odczytu i kontrola wyniku / błędy semantyki |
| L4 · Nadużycie uprawnień i działań | Część wspólna, dokładna zgoda / brak pełnej korelacji |
| L5 · Atak na kontrolę i łańcuch dostaw | Trwałe reguły, limity, metadane / brak podpisów feedu |

<div class="layer-strip"><span>Tożsamość</span><span>Wejście</span><span>Dane</span><span>Działania</span><span>Wyjście</span><span>Zużycie<br>zasobów</span><span>Łańcuch<br>dostaw</span></div>

<div class="warn">Osobne osie: typ scenariusza i warstwa. Bieżące poziomy nieznane. OWASP: powiązania kontroli.</div>

<!-- Sources: docs/threat-model.md and testdata/test-cases.json. Exact layer IDs in user order: identity, input, data, actions, output, consumption, supply_chain. Scenario labels are authored, not observed attacker sophistication. Metadata intake downloads/executes no artifacts. OWASP editions: LLM 2025 and Agentic Applications 2026. -->

---
<!-- _class: compact -->
## Operacje: audyt i zużycie działów

<div class="flow"><div class="node"><strong>Minimalny audyt</strong>Decyzja i wykonanie<br>Trwały zamiar</div><div class="arrow">→</div><div class="node"><strong>Trwałe ponowienie</strong>Zachowana paczka<br>Widoczny backlog i błąd</div><div class="arrow">→</div><div class="node"><strong>Lokalny kolektor</strong>Potwierdzenie po zapisie<br>Deduplikacja ID zdarzeń</div></div>

| Raport działu w wybranym okresie | Co oznacza pomiar |
|---|---|
| Test wystawcy: 6 znanych prób, issuer_v2 | Dział przypisany, dostawca testowy |
| 120 tokenów wejścia / 18 wyjścia | Wybrany okres, taryfa symulowana |
| Niepewny wynik / nieznane zużycie | Rezerwacja pozostaje, sumy mogą być częściowe |

<div class="note">Dev: proponowany merge GitLab nie ma adaptera. Finance: proponowany przelew nie ma adaptera.</div>
<div class="warn">Lokalny odbiór i pliki JSONL/ECS/HEC wymagają osobnego adaptera oraz dowodu dostarczenia do SIEM. Eksport działów nie jest dostępny.</div>

<!-- Sources: accepted docs/department-usage.md at e6ac3564; docs/telemetry-delivery.md. Operator-only bounded selected-period report counts model attempts once, independently of three ledger scopes. Known token/money sums have known_usage_attempts denominator; dispatch_intent is not provider receipt. Accepted issuer QA at cd4c162: six known issuer_v2 provider-fixture attempts, 120 input and 18 output tokens. HR fixture window at 34bf344: two attributed attempts, one known settlement and one uncertain invalid-provider outcome with output withheld. Separate selected windows, never summed. -->

---
<!-- _class: compact standards -->
## Kontrole wspierające obowiązki

| Ramy | Wsparcie techniczne | Obowiązki wdrożenia |
|---|---|---|
| RODO · art. 9 i 22 | Zakres, akceptacja akcji, audyt | Podstawa prawna, udział człowieka |
| AI Act · art. 6, 12, 14, 26 | Audyt, przegląd, odmowa | Cel, nadzór, obowiązki podmiotu |
| DORA | Limity, obsługa awarii | ICT, incydenty, odporność, dostawcy |
| OWASP · LLM 2025 / Agentic 2026 | Dostęp, działania, ujawnienie, zużycie | Ocena zagrożeń i luk systemu |

<div class="warn">AI Act: rekrutacja i ocena kandydatów wymagają analizy celu i wyjątków (art. 6, zał. III pkt 4). HR nie przesądza klasyfikacji.</div>
<div class="note">Oficjalne źródła: <a href="https://eur-lex.europa.eu/eli/reg/2016/679/">RODO</a>, <a href="https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-6">AI Act</a>, <a href="https://www.esma.europa.eu/da/node/207346">DORA</a>, <a href="https://genai.owasp.org/llm-top-10/">OWASP</a>. Kontrole wymagają osobnej oceny zgodności.</div>

<!-- Official sources checked 2026-10-04: https://eur-lex.europa.eu/eli/reg/2016/679/ ; https://www.edpb.europa.eu/system/files/2024-12/edpb_opinion_202428_ai-models_en.pdf ; https://ai-act-service-desk.ec.europa.eu/en/ai-act/annex-3 ; https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-6 ; https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-12 ; https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-14 ; https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-26 ; https://www.esma.europa.eu/da/node/207346 ; https://genai.owasp.org/llm-top-10/ ; https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/ . Interpretive control mapping: docs/standards-evidence.md. Action consent is operator approval, not GDPR data-subject consent. No deadlines or formal legal-classification verdict. -->

---
<!-- _class: compact evidence -->
## Testy kontroli i granice semantyki

<div class="columns"><div><h3>Dowody działania kontroli</h3><table><tr><th>Rodzaj</th><th>Przykład</th></tr><tr><td>Jednostkowe</td><td>Granty, zakresy, heurystyka</td></tr><tr><td>Funkcjonalne</td><td>Odmowa i dokładna zgoda</td></tr><tr><td>Integracyjne</td><td>REST/MCP + transakcje SQLite</td></tr><tr><td>E2E instalacji</td><td>Wheel, przeglądarka i efekty</td></tr></table><p>Baza a370134: 1005 testów, 0 pominiętych.<br>0 przed zgodą → 1 wpis po wznowieniu i powtórce.</p></div><div><h3>Zamrożone realne pomiary Laya</h3><table><tr><th>Korpus</th><th>Standard CPU</th><th>CoreML</th></tr><tr><td>v1 · 26</td><td>7/26 poprawnych</td><td>7/26</td></tr><tr><td>v2 · 28</td><td>15/28 poprawnych</td><td>16/28</td></tr></table><p class="note">V2: CPU/CoreML 7/6 fałszywych alarmów, 4/4 przeoczenia. Przeoczone złośliwe parafrazy.</p><p class="note">V1: 16 nieszkodliwych przypadków wstrzymanych. Rozgrzany CoreML zawiódł. Korpusy są różne.</p></div></div>

<div class="warn"><strong>Realne HR / standard v2: fałszywy alarm.</strong> Zwykły rekord zatrzymany przy READ i SUMMARY. Dwa odczyty wykonane, wyniki wstrzymane. 0 wywołań modelu i 0 wiadomości.</div>
<div class="note">Semantyka domyślnie wyłączona. CoreML eksperymentalny.</div>

<!-- Sources: root acceptance of department PR47, reviewed 40eb409 / merged e6ac3564; docs/semantic-evaluation.md, docs/semantic-v2-evidence.md, docs/release-evidence.md. Never sum overlapping suite counts. V1/v2 corpora/question sets differ; two v2 incomplete cases per backend. Actual installed HR observation at 34bf344 / standard content-role-v2 enforce, checkpoint e4e9ddf21a7b1903b7acffd8814ad4307bf63a67: benign read and summary fresh read both HTTP403 SEMANTIC_BLOCKED executed=true; zero released documents/summaries/provider attempts/outbox. Two tool reservations and four audit events; quota 0 to 2/1000. False positive, unsuitable ordinary HR semantic demo. Report SHA256 af884f87f43e58af5883f44bff0370b0b9bf981aebe496c6e402d53cccfba2de. Accepted runtime base a370134, reviewed c9c47b8 (runtime 34bf344); root gate 1005 zero skips and 18 Node contracts; separate acceptance 140 cases/420 phases; installed credential/local-console and mocked UI-only evidence separately attributed. Final ladder entrypoint reruns passed with failure-entry test retained. Control tests are not detector accuracy. -->

---
<!-- _class: lead closing -->
## Uruchomienie i następna granica

```sh
git clone https://github.com/bsisduck/laya-sec-agent.git
cd laya-sec-agent
./laya install --local-console
```

Przygotuj `uv` i przypięty model Ollama. Otwórz lokalny adres. Konsola bez logowania, wywołania agenta z poświadczeniem.

<div class="target-row"><div class="node"><strong>Lokalny zakres produktu</strong>HR, model i REST/MCP, dokładne zgody, budżety, audyt i kolektor.</div><div class="node proposed"><strong>Następna akceptacja wdrożenia</strong>Firmowy IAM, system HR/poczta, SIEM i izolacja usług. Brak wdrożenia bankowego.</div></div>

[Repozytorium i instrukcje](https://github.com/bsisduck/laya-sec-agent) · PDF i HTML działają offline, bez logowania.

<div class="note">Własny wkład: polityka i wykonanie. Laya, LiteLLM, Ollama, Hermes: zależności. Zespół: [uzupełnij].</div>

<!-- Sources: README.md, docs/local-console.md, docs/local-app.md. Fresh install needs prepared dependencies/assets or network. Prepared restart can be offline. Default install without --local-console retains credential mode on a new installation. Team facts remain user-owned in docs/submission-template.md. No public-demo URL is invented. -->

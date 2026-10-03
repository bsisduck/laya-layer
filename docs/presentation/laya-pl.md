---
marp: true
theme: laya
size: 16:9
paginate: true
header: LAYA SEC LAYER / AGENTGATE
footer: Dowody integracji · 2026-10-03 · Lokalny prototyp · docs/release-evidence.md
---
<!-- _class: lead -->
<div class="kicker">AI Control Layer / HackYeah</div>

# Laya Sec Layer

**Jedna granica polityki dla modeli i działań.**

Kontrola dostępu, limity zasobów, zgoda na dokładne działanie i dowody przed udostępnieniem wyniku.

<div class="note">AgentGate jest bramą. Cezar służy do organizacji prac.</div>

---
## Dwie ścieżki wymagają kontroli

<div class="flow"><div class="node"><strong>Model</strong>Dozwolony alias<br>Kontrola wejścia</div><div class="arrow">→</div><div class="node"><strong>AgentGate</strong>Tożsamość + polityka<br>Budżet + audyt</div><div class="arrow">→</div><div class="node"><strong>Prywatny router</strong>LiteLLM → Ollama<br>Buforowany wynik</div></div>
<div class="flow"><div class="node"><strong>Narzędzia</strong>REST / oficjalny MCP<br>Jawne aliasy</div><div class="arrow">→</div><div class="node"><strong>Ta sama kontrola</strong>ACL + dokładna zgoda<br>Ponowna weryfikacja</div><div class="arrow">→</div><div class="node"><strong>Zarejestrowany efekt</strong>Dokumenty / pamięć<br>Lokalna skrzynka testowa</div></div>

<div class="warn">Wywołanie narzędzia przez model to propozycja. Wykonanie wymaga osobnej autoryzacji.</div>

---
## Reguły deterministyczne decydują

<div class="grid"><div class="card"><h3>Tożsamość i zakres</h3><p>Tenant, rola, agent i główny przebieg wynikają z poświadczenia, nie z rozmowy.</p></div><div class="card"><h3>Ochrona tekstu</h3><p>Maskowanie e-maili i blokowanie testowych sekretów przed ujawnieniem.</p></div><div class="card"><h3>Atomowe limity</h3><p>Wywołania, tokeny i rezerwacje. Niepewny wynik zachowuje rezerwację.</p></div><div class="card"><h3>Zmiany na żywo</h3><p>Walidacja i atomowa aktywacja polityki/feedu. Nieaktualna wersja daje konflikt.</p></div></div>

<div class="note">Obsługiwane formaty testowe, nie uniwersalny DLP. Lokalna taryfa: symulowane zero.</div>

---
## Zgoda dotyczy jednego dokładnego działania

<div class="flow"><div class="node"><strong>Propozycja</strong>Dokładna treść<br>Stały klucz</div><div class="arrow">→</div><div class="node"><strong>Zgoda</strong>Operator sprawdza<br>Fingerprint</div><div class="arrow">→</div><div class="node"><strong>Weryfikacja</strong>Ta sama tożsamość<br>Aktualne reguły</div><div class="arrow">→</div><div class="node"><strong>Wykonanie</strong>Jeden wpis<br>Powtórka bez duplikatu</div></div>

**Oczekiwanie i sama zgoda nie tworzą wpisu w skrzynce.**

Zmieniona treść daje konflikt. Odnowienie zachowuje tożsamość i zużyty budżet.

<div class="warn">Poczta to lokalna skrzynka testowa SQLite. Nie wysyłamy przez SMTP.</div>

---
## Wyniki semantyczne pozostają jawne

| Zamrożony pierwszy przebieg | Standard CPU | Natywny CoreML |
|---|---:|---:|
| v1 · 26 przykładów | 7/26 poprawnych | 7/26 poprawnych |
| v2 · 28 nowych przykładów | 15/28 poprawnych | 16/28 poprawnych |

<div class="warn"><strong>Błędy v2:</strong> 7 / 6 fałszywych alarmów i po 4 przeoczenia. Oba backendy przeoczyły pośrednie złośliwe parafrazy.</div>

<div class="note">V1 zatrzymał wszystkie 16 nieszkodliwych przypadków; rozgrzany przebieg CoreML nie powiódł się. Różne korpusy/pytania nie dowodzą poprawy. CPU v2 w instalacji: allow / wynik po odczycie zatrzymany / tenant deny; limit 0→2. Standard: jawny opt-in; CoreML: eksperymentalny; semantyka domyślnie wyłączona.</div>

---
## Raportowanie z rzeczywistym potwierdzeniem

<div class="flow"><div class="node"><strong>Audyt</strong>Minimalne zdarzenia<br>Rzeczywiste wykonanie</div><div class="arrow">→</div><div class="node"><strong>Trwały sender</strong>Zachowana paczka<br>Powtórka po błędzie</div><div class="arrow">→</div><div class="node"><strong>Lokalny kolektor</strong>Trwałe potwierdzenie<br>Deduplikacja ID</div></div>
<div class="grid"><div class="card"><div class="metric">51</div><div class="label">Lokalnych rekordów · QA instalacji root</div></div><div class="card"><div class="metric">0</div><div class="label">Zaobserwowane opóźnienie w rekordach</div></div></div>

<div class="note">Lokalny protokół Laya HTTP v1; co najmniej raz, nie dokładnie raz. Eksport JSONL/ECS/HEC jest osobną funkcją.</div>

---
## Integracja bankowa wymaga osobnej walidacji

<div class="columns"><div><div class="node"><strong>Dostępne lokalnie</strong>Kontrola modelu i REST/MCP<br>Zgody operatora i aktywne reguły<br>Minimalny eksport i lokalny odbiór</div><p class="note">Loopback ufa hostowi. Bezpośredni dostęp tego samego użytkownika systemu pozostaje poza granicą ochrony.</p></div><div><div class="node proposed"><strong>Proponowane adaptery</strong>Splunk / Elastic / OpenSearch<br>Kafka / Security Hub<br>SSO i magazyn sekretów</div><p class="note">Potrzebne wersje, autoryzacja, dowód indeksowania oraz testy awarii i powtórek.</p></div></div>

<div class="warn">Nie deklarujemy wdrożenia bankowego, certyfikacji SOC/dostawcy ani działającego konektora SIEM.</div>

---
## Odtwarzalne testy i dowody z aplikacji

<div class="grid"><div class="card"><h3>Inwentarz T01–T48</h3><p>Realne testy, zamrożone przykłady, jawne ograniczenia zakresu i brak profilu ANE.</p></div><div class="card"><h3>QA w przeglądarce</h3><p>Root raportuje izolację danych, dokładne zgody pocztowe, reguły, eksport i sesje.</p></div></div>

`make validate` · `scripts/acceptance_matrix.py --run`

<div class="warn">Lokalne podsumowanie: 118 tokenów, jedno wywołanie, 4317 ms z generacją. Jeden pomiar, nie narzut samej kontroli.</div>

<div class="note">Testy reguł i jakość modelu to osobne dowody. Kontrola manifestów i klienci REST/MCP/Hermes są zintegrowani po przeglądzie.</div>

---
<!-- _class: lead -->
## Prototyp do przeglądu. Jawne kolejne bramki.

**Własny wkład:** egzekwowanie polityki, kontrolowane wykonanie, budżety, zgody, aktywne reguły i minimalny audyt.

Laya, LiteLLM, Ollama i Hermes to zależności; Cezar jest narzędziem pracy.

Końcowy przegląd instalacji/CI i akceptacja przedsiębiorstwa pozostają osobne. Zmierzone błędy semantyczne są jawne.

<div class="node"><strong>Dane zgłoszenia — uzupełnia użytkownik</strong>Zespół: [TEAM NAME] · Członkowie (1–6): [MEMBERS]<br>Repozytorium/demo: [URLS] · Ustalenia organizatora: [CONFIRMED DETAILS]</div>

<!-- Notatki: Uzupełnij celowe pola szablonu przed zgłoszeniem. Dopuszczalny język: angielski lub polski. Maksymalnie dziesięć stron PDF. Dokumentacja nie oznacza zgłoszenia ani decyzji o kwalifikowalności. -->

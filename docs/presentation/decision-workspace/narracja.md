# Laya Layer — narracja

10 slajdów · około 5 minut · PL

## 1. Zanim agent wykona działanie

Agent może przeczytać dokument, przygotować odpowiedź albo zaproponować wysłanie wiadomości. Każdy z tych kroków wymaga innej decyzji. Laya Layer wstawia kontrolę przed wykonaniem: sprawdza, kto działa, do jakich danych ma dostęp, jaki będzie skutek i czy mieści się w limicie zasobów. Pokażemy to na lokalnym procesie HR — od prośby do konkretnego śladu w audycie.

Źródła:

- https://github.com/bsisduck/laya-sec-agent/blob/main/docs/architecture.md
- https://github.com/bsisduck/laya-sec-agent/blob/main/docs/hr-workflow.md

## 2. Trzy prośby, trzy decyzje

Zaczynamy od trzech przykładowych rozmów. Odczyt przechodzi tylko po sprawdzeniu zakresu i pozostałych kontroli. Wysłanie danych poza dozwoloną granicę zostaje zatrzymane. Dozwolone zaproszenie może trafić do przeglądu człowieka: odbiorca, temat i treść są widoczne przed zatwierdzeniem. Te historie są opisanymi przykładami, a nie wynikami bieżącej inferencji. Rzeczywiste uruchomienie odbywa się osobno w przestrzeni HR.

Źródła:

- https://github.com/bsisduck/laya-sec-agent/blob/main/docs/hr-workflow.md
- https://github.com/bsisduck/laya-sec-agent/blob/main/docs/scoped-tools.md

## 3. Rozmowa. Dowód. Reguła.

Interfejs prowadzi po trzech pytaniach. Chat pokazuje prośbę i jej decyzję, z opisanymi przykładami oraz wejściem do rzeczywistej pracy HR. Logs pozwala sprawdzić, co brama faktycznie zarejestrowała i czy doszło do wykonania. Workflow tłumaczy ścieżkę decyzji oraz obowiązujące granice. Przykładowe rozmowy nie dopisują zdarzeń do prawdziwych logów.

Źródła:

- https://github.com/bsisduck/laya-sec-agent/blob/main/src/agentgate/web/app.js

## 4. Dwie bramy, jedna polityka

Brama LLM kontroluje to, co trafia do modelu i co może zostać wydane z odpowiedzi. Brama działań obsługuje chronione operacje REST i MCP. Obie korzystają ze wspólnej tożsamości, polityki, budżetu i audytu. Model może zaproponować działanie, ale nie może sam nadać sobie uprawnień. W tej aplikacji wykonawcy obsługują dokumenty, pamięć i lokalny outbox. Ruch poza chronionymi ścieżkami wymaga osobnego zabezpieczenia.

Źródła:

- https://github.com/bsisduck/laya-sec-agent/blob/main/docs/model-gateway.md
- https://github.com/bsisduck/laya-sec-agent/blob/main/docs/scoped-tools.md
- https://github.com/bsisduck/laya-sec-agent/blob/main/docs/architecture.md

## 5. Siedem miejsc kontroli

Pierwszych pięć warstw idzie ścieżką żądania: tożsamość, wejście, dane, działania i wyjście. Zużycie oraz łańcuch dostaw dotyczą całego systemu. To mapa miejsc kontroli, a nie deklaracja pełnej ochrony. W szczegółach Workflow widać, co jest zaimplementowane, częściowe i planowane. Przykładowo przypinanie opisów zewnętrznych narzędzi MCP i Redis dla wielu instancji nie są tu gotowymi funkcjami. Kontrole semantyczne mają udokumentowane błędy.

Źródła:

- https://github.com/bsisduck/laya-sec-agent/blob/main/docs/threat-model.md
- https://github.com/bsisduck/laya-sec-agent/blob/main/src/agentgate/threat_taxonomy.py
- https://github.com/bsisduck/laya-sec-agent/blob/main/docs/semantic-v2-evidence.md

## 6. Skutek wyznacza ścieżkę

Odczyt nie zmienia danych, ale nadal wymaga dostępu, dozwolonej klasy danych, budżetu i pozostałych kontroli. Zapis w lokalnym outboxie wymaga zatwierdzenia dokładnej propozycji. Sama zgoda jeszcze nie wykonuje działania: wznowienie ponownie sprawdza aktualne warunki. Operacje destrukcyjne i nieznane są dziś blokowane, ponieważ nie mają zatwierdzonego wykonawcy. Rozróżniamy zapis od destrukcji; nie każdy zapis jest nieodwracalny. Żadna zgoda człowieka nie omija twardej odmowy polityki.

Źródła:

- https://github.com/bsisduck/laya-sec-agent/blob/main/docs/tool-catalog.md
- https://github.com/bsisduck/laya-sec-agent/blob/main/docs/scoped-tools.md

## 7. Tylko wspólny zakres

Zakres agenta jest przecięciem uprawnień człowieka i agenta. W tym schematycznym przykładzie obie strony mają dostęp do CV, lecz ich pozostałe zasoby się różnią. Przez agenta człowiek nie dostaje nowych uprawnień. Przy wiadomości człowiek sprawdza konkretną migawkę: odbiorcę, temat i treść. Zgoda ma termin ważności. Zmiana treści lub warunków wymaga ponownej oceny. Lokalna konsola bez logowania ufa komputerowi; nie przedstawiamy jej jako firmowego IAM.

Źródła:

- https://github.com/bsisduck/laya-sec-agent/blob/main/docs/delegated-authority.md
- https://github.com/bsisduck/laya-sec-agent/blob/main/docs/hr-workflow.md

## 8. RODO: prawo i rozliczalność

Artykuł 20 dotyczy prawa osoby do przenoszenia danych w odpowiednim formacie. Jego zastosowanie zależy między innymi od podstawy przetwarzania i jego automatyzacji; chronione są także prawa innych osób. Artykuł 30 dotyczy rejestru czynności przetwarzania organizacji: celów, kategorii danych i osób, odbiorców, transferów, retencji oraz zabezpieczeń. Logs pomaga ustalić fakty o chronionych wywołaniach. Eksport technicznego audytu nie jest jednak pełnym eksportem danych osoby ani kompletnym rejestrem czynności. Workflow pokazuje te powiązania i pozostałe wymagania, bez deklaracji zgodności prawnej.

Źródła:

- https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng/
- https://www.edpb.europa.eu/documents/guideline/right-to-data-portability_en
- https://www.edpb.europa.eu/sme/be-compliant/respect-individuals-rights_en
- https://github.com/bsisduck/laya-sec-agent/blob/main/docs/standards-evidence.md

## 9. Testujemy rzeczywisty skutek

Sprawdzamy stan wykonawcy, nie tylko kolor etykiety. Odmowa ma pozostawić zero niedozwolonych skutków. Zatwierdzona wiadomość po wznowieniu tworzy jeden wpis w lokalnym outboxie. Ponowienie tego samego działania nie dodaje duplikatu. Obejmują to testy jednostkowe, funkcjonalne, integracyjne REST i MCP oraz E2E w przeglądarce. Testy z kontrolowanym dostawcą nie mierzą jakości modelu. Osobny zamrożony pomiar standardowego Laya v2 dał 15 poprawnych wyników na 28 przypadków; fałszywe alarmy i przeoczenia pozostają otwartym ograniczeniem. Outbox nie wysyła prawdziwych maili.

Źródła:

- https://github.com/bsisduck/laya-sec-agent/blob/main/tests/test_scoped_tools.py
- https://github.com/bsisduck/laya-sec-agent/blob/main/tests/test_authority.py
- https://github.com/bsisduck/laya-sec-agent/blob/main/tests/frontend/hr_flow.py
- https://github.com/bsisduck/laya-sec-agent/blob/main/docs/semantic-v2-evidence.md

## 10. Zobacz granicę działania

Teraz przejdźmy do aplikacji. W Chat wybieramy opisany przykład i odróżniamy go od rzeczywistego uruchomienia HR. W Logs szukamy zdarzenia z tego uruchomienia i sprawdzamy, czy działanie faktycznie się wykonało. W Workflow wracamy do warstwy i reguły, która doprowadziła do decyzji. To jest lokalny prototyp ze sprawdzalnymi granicami. Kolejny etap wdrożenia wymaga dopasowania do firmowych danych, IAM, odbioru telemetrii i osobnej akceptacji jakości modeli.

Źródła:

- https://github.com/bsisduck/laya-sec-agent/blob/main/docs/operations-workspace-validation.md
- https://github.com/bsisduck/laya-sec-agent/blob/main/docs/release-evidence.md

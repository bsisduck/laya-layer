/** Editable ten-slide Polish deck. Usage: NODE_PATH=<pptxgenjs-4.0.1-dir>/node_modules node build.cjs <output.pptx> */
const pptxgen = require('pptxgenjs');
const fs = require('node:fs');
const JSZip = require('jszip');
const path = require('node:path');
const out = process.argv[2];
if (!out || !out.endsWith('.pptx')) throw new Error('Pass an output .pptx path');
const pptx = new pptxgen();
pptx.layout = 'LAYOUT_WIDE';
pptx.author = 'Laya Layer';
pptx.subject = 'Chat, Logs, Workflow — kontrola działań agenta';
pptx.title = 'Laya Layer — przed wykonaniem';
pptx.company = 'Laya Layer';
pptx.lang = 'pl-PL';
pptx.theme = {headFontFace:'Avenir Next', bodyFontFace:'Avenir Next', lang:'pl-PL'};
const C = {paper:'F4F3ED', ink:'233C32', orange:'C54D1B', muted:'5F6C62', line:'CBD5CA', white:'FFFFFF', green:'326149', red:'A73728', pale:'E4EBDF', peach:'F7E5D6'};
const W=13.333333,H=7.5;
const notes=[];
function rect(s,x,y,w,h,fill,stroke=fill,width=0){s.addShape(pptx.ShapeType.rect,{x,y,w,h,fill:{color:fill},line:{color:stroke,width},radius:0});}
function line(s,x,y,w,h=0,color=C.line,width=1,arrow=false){s.addShape(pptx.ShapeType.line,{x,y,w,h,line:{color,width,...(arrow?{endArrowType:'triangle'}:{})}});}
function t(s,text,x,y,w,h,size=24,color=C.ink,bold=false,extra={}){s.addText(text,{x,y,w,h,fontFace:'Avenir Next',fontSize:size,color,bold,margin:0,breakLine:false,paraSpaceAfterPt:0,valign:'mid',...extra});}
function circle(s,x,y,d,color){s.addShape(pptx.ShapeType.ellipse,{x,y,w:d,h:d,fill:{color},line:{color,width:0}});}
function number(s,n,x,y,color=C.ink){t(s,String(n).padStart(2,'0'),x,y,1.1,.8,44,color,true);}
function small(s,text,x,y,w=11,color=C.muted){t(s,text,x,y,w,.38,14,color);}
function base(title,{dark=false}={}){const s=pptx.addSlide();s.background={color:dark?C.ink:C.paper};const ink=dark?C.paper:C.ink;
 if(title)t(s,title,.7,.57,11.9,.85,35,ink,true);
 small(s,'LAYA LAYER',.7,6.92,2,dark?'C2CEBF':C.muted);
 small(s,`${String(pptx._slides.length).padStart(2,'0')} / 10`,11.7,6.92,.9,dark?'C2CEBF':C.muted);
 return s;}
function note(s,title,body,sources=[]){s.addNotes(`${body}\n\nŹródła / dowody:\n${sources.join('\n')}`);notes.push({title,body,sources});}
function label(s,text,x,y,w,color=C.green){t(s,text,x,y,w,.4,16,color,true);}
const repo='https://github.com/bsisduck/laya-sec-agent/blob/main/';
// 1 — restrained cover, native vector boundary motif.
{
 const s=base(null,{dark:true});
 t(s,'Laya Layer',.7,1.06,10,1.13,66,C.paper,true);
 t(s,'Zanim agent\nwykona działanie',.74,2.55,10.9,1.8,43,C.paper);
 rect(s,11.95,1.12,.12,4.9,C.orange);
 circle(s,11.7,2.82,.62,C.orange);
 t(s,'TOŻSAMOŚĆ  /  DANE  /  SKUTEK  /  LIMIT',.75,5.62,10.8,.6,18,'C2CEBF');
 note(s,'Zanim agent wykona działanie','Agent może przeczytać dokument, przygotować odpowiedź albo zaproponować wysłanie wiadomości. Każdy z tych kroków wymaga innej decyzji. Laya Layer wstawia kontrolę przed wykonaniem: sprawdza, kto działa, do jakich danych ma dostęp, jaki będzie skutek i czy mieści się w limicie zasobów. Pokażemy to na lokalnym procesie HR — od prośby do konkretnego śladu w audycie.',[repo+'docs/architecture.md',repo+'docs/hr-workflow.md']);
}
// 2 — three real decision classes, explicitly authored scenarios.
{
 const s=base('Trzy prośby, trzy decyzje');
 small(s,'Scenariusze HR · dane fikcyjne',.73,1.56);
 const rows=[['ALLOWED','Podsumuj dostępne CV','Odczyt w nadanym zakresie',C.green],['BLOCKED','Wyślij dane poza dozwolony zakres','Brak wykonania',C.red],['ESCALATED','Przygotuj zaproszenie na rozmowę','Najpierw przegląd dokładnej wiadomości',C.orange]];
 rows.forEach((r,i)=>{const y=2.3+i*1.23; circle(s,.77,y+.12,.14,r[3]);label(s,r[0],1.12,y,2.15,r[3]);t(s,r[1],3.43,y-.08,8.3,.55,25);small(s,r[2],3.43,y+.53,8);if(i<2)line(s,.75,y+.96,11.8);});
 note(s,'Trzy prośby, trzy decyzje','Zaczynamy od trzech przykładowych rozmów. Odczyt przechodzi tylko po sprawdzeniu zakresu i pozostałych kontroli. Wysłanie danych poza dozwoloną granicę zostaje zatrzymane. Dozwolone zaproszenie może trafić do przeglądu człowieka: odbiorca, temat i treść są widoczne przed zatwierdzeniem. Te historie są opisanymi przykładami, a nie wynikami bieżącej inferencji. Rzeczywiste uruchomienie odbywa się osobno w przestrzeni HR.',[repo+'docs/hr-workflow.md',repo+'docs/scoped-tools.md']);
}
// 3 — three application surfaces as a single journey.
{
 const s=base('Rozmowa. Dowód. Reguła.');
 const cols=[['Chat','Co chcę zrobić?','Prośba + decyzja'],['Logs','Co się wydarzyło?','Przebieg + rzeczywisty skutek'],['Workflow','Dlaczego?','Warstwy + polityka']];
 cols.forEach((r,i)=>{const x=.75+i*4.18;number(s,i+1,x,2.12,i===0?C.orange:C.ink);t(s,r[0],x,3.15,3.72,.7,38,C.ink,true);t(s,r[1],x,4.12,3.85,.5,23);small(s,r[2],x,4.81,3.9);if(i<2)line(s,x+3.72,2.2,0,3.23);});
 note(s,'Rozmowa. Dowód. Reguła.','Interfejs prowadzi po trzech pytaniach. Chat pokazuje prośbę i jej decyzję, z opisanymi przykładami oraz wejściem do rzeczywistej pracy HR. Logs pozwala sprawdzić, co brama faktycznie zarejestrowała i czy doszło do wykonania. Workflow tłumaczy ścieżkę decyzji oraz obowiązujące granice. Przykładowe rozmowy nie dopisują zdarzeń do prawdziwych logów.',[repo+'src/agentgate/web/app.js']);
}
// 4 — both gateways, shared authority and evidence.
{
 const s=base('Dwie bramy, jedna polityka');
 const xs=[.75,5,9.25], bw=3.33;
 [['Agent','Brama LLM','Model'],['Wywołanie','Brama działań','Wykonawca']].forEach((row,j)=>{const y=2.2+j*2.35;row.forEach((txt,i)=>{rect(s,xs[i],y,bw,.88,i===1?C.ink:C.white);t(s,txt,xs[i]+.2,y+.1,bw-.4,.65,24,i===1?C.paper:C.ink,true);if(i<2)line(s,xs[i]+bw+.12,y+.44,.63,0,C.muted,1.5,true);});});
 small(s,'Wejście · model · wyjście',5.02,3.16,4.5);
 small(s,'REST / MCP',.75,5.54,3.3);small(s,'Dokumenty · lokalny outbox',9.25,5.54,3.35);
 rect(s,.75,3.79,11.83,.5,C.pale);t(s,'TOŻSAMOŚĆ     /     POLITYKA     /     BUDŻET     /     AUDYT',.98,3.84,11.37,.38,17,C.ink,true,{align:'center'});
 note(s,'Dwie bramy, jedna polityka','Brama LLM kontroluje to, co trafia do modelu i co może zostać wydane z odpowiedzi. Brama działań obsługuje chronione operacje REST i MCP. Obie korzystają ze wspólnej tożsamości, polityki, budżetu i audytu. Model może zaproponować działanie, ale nie może sam nadać sobie uprawnień. W tej aplikacji wykonawcy obsługują dokumenty, pamięć i lokalny outbox. Ruch poza chronionymi ścieżkami wymaga osobnego zabezpieczenia.',[repo+'docs/model-gateway.md',repo+'docs/scoped-tools.md',repo+'docs/architecture.md']);
}
// 5 — seven layers: five in order, two across the system.
{
 const s=base('Siedem miejsc kontroli');
 const layers=[['Tożsamość','Kto działa?'],['Wejście','Co czyta?'],['Dane','Jaki zakres?'],['Działania','Jaki skutek?'],['Wyjście','Co wydajemy?']];
 layers.forEach((r,i)=>{const x=.75+i*2.41;number(s,i+1,x,2.12,i===3?C.orange:C.ink);t(s,r[0],x,3.06,2.22,.45,22,C.ink,true);small(s,r[1],x,3.65,2.25);if(i<4)line(s,x+1.74,2.6,.43,0,C.muted,1.4,true);});
 line(s,.75,4.42,11.83);
 label(s,'06   ZUŻYCIE',.77,4.81,3.25);t(s,'Tokeny · koszt · czas',4.1,4.75,8,.55,25);
 label(s,'07   ŁAŃCUCH DOSTAW',.77,5.65,3.6);t(s,'Zależności · feed · polityka',4.1,5.57,8,.6,25);
 note(s,'Siedem miejsc kontroli','Pierwszych pięć warstw idzie ścieżką żądania: tożsamość, wejście, dane, działania i wyjście. Zużycie oraz łańcuch dostaw dotyczą całego systemu. To mapa miejsc kontroli, a nie deklaracja pełnej ochrony. W szczegółach Workflow widać, co jest zaimplementowane, częściowe i planowane. Przykładowo przypinanie opisów zewnętrznych narzędzi MCP i Redis dla wielu instancji nie są tu gotowymi funkcjami. Kontrole semantyczne mają udokumentowane błędy.',[repo+'docs/threat-model.md',repo+'src/agentgate/threat_taxonomy.py',repo+'docs/semantic-v2-evidence.md']);
}
// 6 — operation consequences, precise deny vs review semantics.
{
 const s=base('Skutek wyznacza ścieżkę');
 const rows=[['ODCZYT','Sprawdź zakres','Odczyt + audyt',C.green],['ZAPIS','Dokładna zgoda¹','Wznowienie + audyt',C.orange],['DESTRUKCYJNE','Brak adaptera','Blokada',C.red]];
 rows.forEach((r,i)=>{const y=2.08+i*1.22;label(s,r[0],.76,y+.1,2.8,r[3]);rect(s,3.85,y,3.6,.74,C.white);t(s,r[1],4.04,y+.08,3.2,.53,23);line(s,7.62,y+.37,.78,0,r[3],1.5,true);t(s,r[2],8.72,y+.08,3.82,.53,25,r[3],true);});
 small(s,'¹ Gdy polityka dopuszcza działanie. Zgoda nie uchyla odmowy.',.76,6.04,11.6);
 note(s,'Skutek wyznacza ścieżkę','Odczyt nie zmienia danych, ale nadal wymaga dostępu, dozwolonej klasy danych, budżetu i pozostałych kontroli. Zapis w lokalnym outboxie wymaga zatwierdzenia dokładnej propozycji. Sama zgoda jeszcze nie wykonuje działania: wznowienie ponownie sprawdza aktualne warunki. Operacje destrukcyjne i nieznane są dziś blokowane, ponieważ nie mają zatwierdzonego wykonawcy. Rozróżniamy zapis od destrukcji; nie każdy zapis jest nieodwracalny. Żadna zgoda człowieka nie omija twardej odmowy polityki.',[repo+'docs/tool-catalog.md',repo+'docs/scoped-tools.md']);
}
// 7 — authority intersection and immutable action consent.
{
 const s=base('Tylko wspólny zakres');
 rect(s,.75,2.12,3.08,1.44,C.white);t(s,'Człowiek',.99,2.3,2.64,.44,25,C.ink,true);small(s,'CV + notatki HR',.99,2.94,2.64);
 t(s,'∩',4.06,2.34,.6,.8,40,C.orange,false,{align:'center'});
 rect(s,4.95,2.12,3.08,1.44,C.white);t(s,'Agent',5.19,2.3,2.64,.44,25,C.ink,true);small(s,'CV + finanse',5.19,2.94,2.64);
 t(s,'=',8.25,2.34,.6,.8,37,C.orange,false,{align:'center'});
 rect(s,9.14,2.12,3.44,1.44,C.ink);t(s,'Tylko CV',9.4,2.51,2.92,.6,30,C.paper,true);
 t(s,'Zgoda dotyczy jednej propozycji',.76,4.44,11.6,.6,30,C.ink,true);
 t(s,'Odbiorca   /   Temat   /   Treść   /   Termin',.77,5.32,11.6,.57,24,C.muted);
 note(s,'Tylko wspólny zakres','Zakres agenta jest przecięciem uprawnień człowieka i agenta. W tym schematycznym przykładzie obie strony mają dostęp do CV, lecz ich pozostałe zasoby się różnią. Przez agenta człowiek nie dostaje nowych uprawnień. Przy wiadomości człowiek sprawdza konkretną migawkę: odbiorcę, temat i treść. Zgoda ma termin ważności. Zmiana treści lub warunków wymaga ponownej oceny. Lokalna konsola bez logowania ufa komputerowi; nie przedstawiamy jej jako firmowego IAM.',[repo+'docs/delegated-authority.md',repo+'docs/hr-workflow.md']);
}
// 8 — distinct GDPR purposes; evidence support, not compliance certification.
{
 const s=base('RODO: prawo i rozliczalność');
 number(s,20,.76,2.01,C.orange);number(s,30,7.02,2.01,C.orange);
 t(s,'Przenoszenie danych',.76,3.01,5.55,.6,29,C.ink,true);
 t(s,'Prawo osoby',.77,3.85,5.5,.52,24);small(s,'Dane w formacie do ponownego użycia',.77,4.55,5.7);
 t(s,'Rejestr czynności',7.02,3.01,5.55,.6,29,C.ink,true);
 t(s,'Odpowiedzialność organizacji',7.03,3.85,5.55,.52,22);small(s,'Cele · kategorie · odbiorcy · retencja',7.03,4.55,5.5);
 line(s,6.46,2.11,0,3.12);
 t(s,'Audyt bramy wspiera ocenę. Nie zastępuje tych procesów.',.76,5.8,11.9,.56,21,C.muted);
 note(s,'RODO: prawo i rozliczalność','Artykuł 20 dotyczy prawa osoby do przenoszenia danych w odpowiednim formacie. Jego zastosowanie zależy między innymi od podstawy przetwarzania i jego automatyzacji; chronione są także prawa innych osób. Artykuł 30 dotyczy rejestru czynności przetwarzania organizacji: celów, kategorii danych i osób, odbiorców, transferów, retencji oraz zabezpieczeń. Logs pomaga ustalić fakty o chronionych wywołaniach. Eksport technicznego audytu nie jest jednak pełnym eksportem danych osoby ani kompletnym rejestrem czynności. Workflow pokazuje te powiązania i pozostałe wymagania, bez deklaracji zgodności prawnej.',[
 'https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng/',
 'https://www.edpb.europa.eu/documents/guideline/right-to-data-portability_en',
 'https://www.edpb.europa.eu/sme/be-compliant/respect-individuals-rights_en',
 repo+'docs/standards-evidence.md']);
}
// 9 — executable evidence, no fabricated precision/coverage metric.
{
 const s=base('Testujemy rzeczywisty skutek');
 const evidence=[['Odmowa','0','niedozwolonych\nefektów'],['Zgoda + wznowienie','1','wpis w lokalnym\noutboxie'],['Ponowienie','0','duplikatów']];
 evidence.forEach((r,i)=>{const x=.76+i*4.19;label(s,r[0],x,2.1,3.95);t(s,r[1],x,2.99,3.8,1.36,80,i===1?C.orange:C.ink,true);t(s,r[2],x,4.77,3.8,.9,22,C.ink,false,{valign:'top'});});
 small(s,'Testy deterministyczne · REST / MCP / przeglądarka. Jakość modelu: osobny pomiar.',.76,6.2,11.8);
 note(s,'Testujemy rzeczywisty skutek','Sprawdzamy stan wykonawcy, nie tylko kolor etykiety. Odmowa ma pozostawić zero niedozwolonych skutków. Zatwierdzona wiadomość po wznowieniu tworzy jeden wpis w lokalnym outboxie. Ponowienie tego samego działania nie dodaje duplikatu. Obejmują to testy jednostkowe, funkcjonalne, integracyjne REST i MCP oraz E2E w przeglądarce. Testy z kontrolowanym dostawcą nie mierzą jakości modelu. Osobny zamrożony pomiar standardowego Laya v2 dał 15 poprawnych wyników na 28 przypadków; fałszywe alarmy i przeoczenia pozostają otwartym ograniczeniem. Outbox nie wysyła prawdziwych maili.',[repo+'tests/test_scoped_tools.py',repo+'tests/test_authority.py',repo+'tests/frontend/hr_flow.py',repo+'docs/semantic-v2-evidence.md']);
}
// 10 — demonstration handoff with a single visual rule.
{
 const s=base(null,{dark:true});
 t(s,'Zobacz granicę\ndziałania',.75,1.02,11.8,1.76,54,C.paper,true);
 const xs=[.78,5.06,9.52];['Chat','Logs','Workflow'].forEach((txt,i)=>{t(s,txt,xs[i],4.06,i===2?3.13:2.4,.7,32,C.paper,true);if(i<2)line(s,xs[i]+2.63,4.42,1.03,0,C.orange,2,true);});
 small(s,'Prośba',.8,4.98,3,'C2CEBF');small(s,'Rzeczywisty przebieg',5.08,4.98,4,'C2CEBF');small(s,'Powód decyzji',9.53,4.98,3,'C2CEBF');
 small(s,'Lokalny prototyp · syntetyczne dane · kontrolowane wykonanie',.8,6.13,11.7,'C2CEBF');
 note(s,'Zobacz granicę działania','Teraz przejdźmy do aplikacji. W Chat wybieramy opisany przykład i odróżniamy go od rzeczywistego uruchomienia HR. W Logs szukamy zdarzenia z tego uruchomienia i sprawdzamy, czy działanie faktycznie się wykonało. W Workflow wracamy do warstwy i reguły, która doprowadziła do decyzji. To jest lokalny prototyp ze sprawdzalnymi granicami. Kolejny etap wdrożenia wymaga dopasowania do firmowych danych, IAM, odbioru telemetrii i osobnej akceptacji jakości modeli.',[repo+'docs/operations-workspace-validation.md',repo+'docs/release-evidence.md']);
}
if (pptx._slides.length!==10) throw new Error('Exactly ten slides required');
fs.mkdirSync(path.dirname(path.resolve(out)),{recursive:true});
pptx.writeFile({fileName:out}).then(async()=>{
 // PptxGenJS 4.0.1 can emit content-type declarations for absent slide masters.
 // Remove only those dangling declarations; never alter real parts or relationships.
 const zip = await JSZip.loadAsync(fs.readFileSync(out));
 const manifest = await zip.file('[Content_Types].xml').async('string');
 const cleaned = manifest.replace(/<Override\b[^>]*\/>/g, entry => {
   const part = entry.match(/PartName="([^"]+)"/)?.[1];
   if (!part || zip.file(part.replace(/^\//,''))) return entry;
   if (!/^\/ppt\/slideMasters\/slideMaster\d+\.xml$/.test(part)) throw new Error(`Unexpected missing package part: ${part}`);
   return '';
 });
 zip.file('[Content_Types].xml', cleaned);
 fs.writeFileSync(out, await zip.generateAsync({type:'nodebuffer',compression:'DEFLATE'}));
 const md='# Laya Layer — narracja\n\n10 slajdów · około 5 minut · PL\n\n'+notes.map((n,i)=>`## ${i+1}. ${n.title}\n\n${n.body}\n\nŹródła:\n\n${n.sources.map(x=>'- '+x).join('\n')}\n`).join('\n');
 fs.writeFileSync(path.join(path.dirname(out),'Laya Layer — narracja.md'),md);
 console.log(JSON.stringify({slides:10,pptx:out,nativeText:true,speakerNotes:notes.length}));
});

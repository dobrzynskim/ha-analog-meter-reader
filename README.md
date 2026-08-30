# Analog Meter Reader

Integracja Home Assistant, która odczytuje wskazanie **analogowego licznika**
(wody, gazu — dowolnego z bębenkowym paskiem cyfr) ze zdjęcia kamery, przy
pomocy AI vision (Gemini). Dla liczników bez żadnego API/łączności — jedyny
sposób na wpięcie ich do Home Assistant to właśnie odczyt obrazu.

Źródłem obrazu może być zwykły URL snapshotu **albo dowolna istniejąca
encja `camera` w HA** — RTSP, ONVIF, Frigate, go2rtc, WebRTC, cokolwiek, co
HA już potrafi zamienić w klatkę. Nie trzeba znać surowego adresu kamery ani
osobno ogarniać jej autoryzacji.

> ⚠️ **Status: wersja wczesna.** Logika odczytu/walidacji jest przeniesiona
> z działającego od dłuższego czasu skryptu cron + MQTT + szablon Jinja w HA
> (patrz niżej) — to nie pierwszy raz, kiedy ktoś próbuje odczytać ten
> konkretny licznik. Sama integracja (config_flow, encje, Options Flow) jest
> jednak nowa i nie była jeszcze uruchomiona na żywo w HA.

## Skąd to się wzięło

Wcześniej to samo robiły trzy osobne warstwy: cron co 10 min pobierający
zdjęcie i pytający Gemini, publikacja na MQTT, i osobny szablon Jinja po
stronie Home Assistant powtarzający *tę samą* walidację "licznik się nie
cofa" — a "ostatni dobry odczyt" trzymany w pliku na dysku residentnie w
skrypcie i jednocześnie w helperze `input_number` po stronie HA. Ta
integracja konsoliduje to w jedno miejsce: jeden koordynator, jedna funkcja
walidująca (z testami), stan trwały przez `homeassistant.helpers.storage.Store`
zamiast pliku + helpera.

## Co udostępnia

- **`sensor`** — skorygowany odczyt licznika (`device_class` woda/gaz,
  `state_class: total_increasing`), z surowym odczytem AI i informacją o
  odrzuceniu w atrybutach.
- **`binary_sensor`** — "Podejrzany odczyt": włączony, gdy ostatni surowy
  odczyt AI został odrzucony (cofnięcie się albo nierealistyczny skok) —
  gotowy trigger na powiadomienie. W atrybutach ma surowy odczyt/odpowiedź
  AI, które go wywołały - widać od razu, co konkretnie AI odczytało.
- **`camera`** — ostatnie pobrane zdjęcie (po odbiciu lustrzanym, jeśli
  włączone) — podgląd na dashboardzie bez trzymania osobnego pliku na dysku.
- **`number`** — trzy encje w sekcji "Konfiguracja" na karcie urządzenia:
  - **ręczna korekta**: wpisana wartość od razu zastępuje bieżący odczyt i
    staje się nowym punktem odniesienia dla walidacji. Przydatne przy serii
    odrzuconych odczytów pod rząd (np. AI utknęło na złej wartości) albo po
    fizycznej wymianie/zerowaniu licznika.
  - **częstotliwość odczytu** (1-1440 min) i **maksymalny realistyczny
    wzrost między odczytami** — te same wartości co w dialogu "Konfiguruj"
    (Options Flow) — zmiana w jednym miejscu widoczna jest też w drugim,
    oba zapisują się do tego samego ustawienia i przetrwają restart HA.
- **`button`** — "Wymuś odczyt teraz": natychmiastowe pobranie zdjęcia i
  odczyt, bez czekania na kolejny zaplanowany cykl **i bez względu na
  godziny ciszy** (świadomie omija to okno, w odróżnieniu od zwykłego
  zaplanowanego cyklu).
- **`text`** — godziny ciszy (początek/koniec), ta sama wartość co w
  Options Flow, tylko widoczna wprost na karcie urządzenia.

Integracja sama pilnuje jakości źródła: po **6 kolejnych** odrzuconych/
niepewnych odczytach pod rząd zgłasza **Repair Issue** ("możliwy problem z
kalibracją") w Ustawienia → System → Naprawy — zwykle oznacza to, że kamera
się poruszyła albo zmieniło się oświetlenie. Znika automatycznie, gdy
znowu pojawi się dobry odczyt.

## Jak to działa

Co `scan_interval_minutes` (domyślnie 10 min): pobierz zdjęcie z kamery →
ewentualnie odbij lustrzanie → przytnij do skonfigurowanej ramki wokół paska
cyfr i powiększ ×4 → wyślij do Gemini Vision z promptem opisującym układ
cyfr → sparsuj odpowiedź → zwaliduj względem ostatniego zaakceptowanego
odczytu (licznik nigdy się nie cofa; zbyt duży skok w jednym cyklu = albo
korekta przesuniętego przecinka, albo odrzucenie i pozostanie przy starej
wartości).

## Instalacja

1. Skopiuj `custom_components/analog_meter_reader` do `<config>/custom_components/`.
2. Zrestartuj Home Assistant.
3. Ustawienia → Urządzenia i usługi → Dodaj integrację → "Analog Meter Reader".
4. **Krok 1:** dokładnie jedno źródło obrazu — albo adres URL zwracający
   pojedyncze zdjęcie z kamery, albo istniejąca encja `camera` w HA (wybór z
   listy) — plus klucz API Gemini, typ licznika/jednostka, czy zdjęcie
   wymaga odbicia lustrzanego.
5. **Krok 2 — kalibracja z podglądem:** formularz HA nie umożliwia
   interaktywnego przeciągania ramki na obrazku (brak JS/canvas w
   config_flow), więc zamiast tego pokazuje pełne zdjęcie z naniesioną
   siatką współrzędnych co 50px — z niej odczytujesz piksele rogów paska
   cyfr. Wpisujesz je i zapisujesz: zobaczysz swoją ramkę zaznaczoną na
   czerwono na pełnym zdjęciu (do korekty) oraz osobny podgląd samego
   przycięcia, powiększony ×4 (dokładnie tak, jak trafia do AI, do
   sprawdzenia czytelności cyfr). Poprawiasz współrzędne w kolejnych
   próbach, aż będzie dobrze, i dopiero wtedy zaznaczasz "Zatwierdź". Ramka
   poza granicami zdjęcia jest odrzucana od razu, z komunikatem błędu, nie
   cichym ucięciem.

Nie trzeba niczego mierzyć w zewnętrznym edytorze grafiki — kalibracja
dzieje się w całości w formularzu dodawania integracji, na podstawie
siatki naniesionej na zdjęcie.

## Ustawienia (Options Flow)

Bez zmiany kodu, przez **Konfiguruj** przy integracji:

- częstotliwość odczytu (domyślnie 10 min)
- maksymalny realistyczny wzrost między odczytami (domyślnie 2.0 — dostosuj
  do jednostki i częstotliwości Twojego licznika)
- własny prompt AI (domyślny jest dopasowany do liczników z czarnymi
  cyframi pełnych jednostek i czerwonymi cyframi ułamka — inny układ może
  wymagać innego opisu)
- **godziny ciszy** (opcjonalnie, format GG:MM) — w tym oknie integracja
  całkowicie pomija cykl (nie pobiera zdjęcia, nie pyta AI) i zachowuje
  ostatnią wartość. Obsługuje okno przechodzące przez północ (np. 23:00 →
  06:00). Puste pola = wyłączone, odpytywanie non-stop jak dotąd. Realnie
  ogranicza liczbę (płatnych) zapytań do Gemini w porach, gdy zmiana
  odczytu jest mało prawdopodobna.
- **model Gemini** (domyślnie `gemini-3.6-flash`) — konfigurowalny, nie
  wpisany na sztywno w kodzie. Google regularnie wycofuje starsze modele
  dla nowych kluczy API (tak stało się z `gemini-2.5-flash` w trakcie
  pierwszego uruchomienia tej integracji - patrz historia commitów) - gdy
  to się powtórzy, zmiana modelu nie wymaga edycji kodu ani redeployu.

## Diagnostyka

**Pobierz diagnostykę** przy integracji eksportuje ostatnie dane koordynatora
do zgłoszenia buga — klucz API i adres kamery (mógłby zdradzić topologię
sieci domowej) są automatycznie maskowane.

## Znane ograniczenia

- Wymaga klucza API Gemini (darmowy tier ma limity zapytań/dzień — przy
  częstym odpytywaniu warto to mieć na uwadze).
- Jakość odczytu zależy od ostrości/oświetlenia zdjęcia z kamery i
  poprawności ramki przycięcia — to nie jest deterministyczny OCR, tylko
  odpowiedź modelu językowego.
- Domyślny prompt i regex wartości (`XXX.XXX`) zakładają format licznika z
  częścią całkowitą i ułamkową rozdzieloną kropką — inny format wymaga
  własnego promptu (Options Flow) i ewentualnie zmiany `VALUE_RE` w kodzie.

## Licencja

MIT — zobacz [LICENSE](LICENSE).

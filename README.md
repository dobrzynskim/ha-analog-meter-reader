# Analog Meter Reader

Integracja Home Assistant, która odczytuje wskazanie **analogowego licznika**
(wody, gazu — dowolnego z bębenkowym paskiem cyfr) ze zdjęcia zwykłej kamery
IP, przy pomocy AI vision (Gemini). Dla liczników bez żadnego API/łączności —
jedyny sposób na wpięcie ich do Home Assistant to właśnie odczyt obrazu.

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
  gotowy trigger na powiadomienie.
- **`camera`** — ostatnie pobrane zdjęcie (po odbiciu lustrzanym, jeśli
  włączone) — podgląd na dashboardzie bez trzymania osobnego pliku na dysku.

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
4. **Krok 1:** adres URL zwracający pojedyncze zdjęcie z kamery, klucz API
   Gemini, typ licznika/jednostka, czy zdjęcie wymaga odbicia lustrzanego.
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

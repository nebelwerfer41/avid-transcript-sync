# Avid Transcript Sync — 0.1

Web app statica per sincronizzare trascrizioni italiane con video locali. Implementazione autonoma: il sorgente del precedente convertitore Word non era disponibile. Non invia documenti o video a un server. Le librerie per PDF/DOCX vengono caricate da CDN; TXT, editing ed export funzionano senza CDN.

## Avvio

```sh
python3 -m http.server 8000
```
Aprire http://localhost:8000. Non aprire index.html direttamente con file:// (moduli ES). Node non serve per l'uso normale.

## Flusso

1. Importare PDF con testo selezionabile, DOCX o TXT. Per scansioni, eseguire prima OCR italiano (es. OCRmyPDF: `ocrmypdf -l ita originale.pdf ricercabile.pdf`). Controllare l'ordine delle colonne, gli speaker e i timecode nella textarea. Il parser riconosce intestazioni Prima/Seconda/Terza videocassetta e righe Ore HH:MM:SS. I nomi LS, ALL, DI MAURO sono riconosciuti; altri nomi in maiuscolo sono euristici.
2. Generare. I timecode si riferiscono all'inizio del blocco successivo; il primo timecode diventa l'offset iniziale. La fine provvisoria è modificabile. La demo contiene un timecode intermedio inventato per mostrare il funzionamento, non un dato documentale.
3. Selezionare clip e video/audio. Impostare il TC effettivo del frame zero e la durata. Ridistribuire: il testo viene ponderato per caratteri tra ancoraggi, con durata massima. L'eventuale silenzio non viene stimato dall'audio. Gli ancoraggi stampati vengono traslati quando cambia l'offset. I sottotitoli bloccati mantengono la loro posizione relativa al video.
4. Selezionare una battuta, ascoltare e impostare IN/OUT; trascinare corpo/bordi sulla timeline. Ancora IN (Invio) fissa l'inizio al cursore e redistribuisce le altre battute. Bloccare dopo verifica per mantenere entrambi gli estremi. Il pulsante loop ripete la battuta. Le frecce avanzano/arretrano di un frame nominale. J salta indietro di 2s, K pausa, L play. Salvare spesso il JSON: il video va ricollegato dopo riapertura.
5. Export della clip selezionata: Avid DS Caption TXT (SubCap, timecode assoluto), STL Spruce testuale (legacy, non EBU N19), SRT (relativo al video), marker TXT (IN green / OUT red). Importare DS Caption nel pannello Caption Files dell'effetto SubCap; il TC deve corrispondere alla sequenza. Verificare marker e STL legacy con la propria versione di Avid. Non è implementato EBU STL binario. Il controllo impedisce export con overlap, durate nulle e fuori clip. FPS interi non-drop-frame; default 25.

## Limiti

- PDF scansiti richiedono OCR esterno; PDF a doppia pagina possono richiedere correzione dell'ordine.
- La forma d'onda dipende da decodeAudioData: alcuni contenitori video non sono decodificabili e file lunghi richiedono memoria. La timeline resta utilizzabile; si può usare una copia audio separata. Limite canvas 32000 pixel: ridurre zoom per clip lunghe.
- Niente forced alignment, filtri audio, undo o recupero automatico dei progetti in questa versione. La precisione di seek dipende dal browser e dal codec.
- Test automatici del motore, non test end-to-end con Avid o video reali. Non sostituisce la verifica di una trascrizione giudiziaria.

## Test

```sh
node test.mjs
```

## GitHub Pages

```sh
git init -b main
git add .
git commit -m "Initial transcript synchronization editor"
git remote add origin https://github.com/USERNAME/avid-transcript-sync.git
git push -u origin main
```
Creare prima il repository vuoto su GitHub. Settings > Pages > Deploy from a branch > main > / (root).

## v0.2
- Il canvas è confinato nella timeline scrollabile: lo zoom non modifica la larghezza del player (massimo 520 px).
- Colori per parlante, conservati nel progetto JSON; si applicano a timeline, elenco e anteprima, non ai formati Avid testuali.
- Normalizzazione conservativa OCR dei nomi ALL, DI MAURO, LINDA, LS, ORM, spazi e righe PDF; pulsante Pulisci testo OCR. Il testo prima della prima intestazione videocassetta riconosciuta non entra nei sottotitoli.
- Il PDF può contenere errori OCR anche nel corpo delle battute: la pulizia non è un nuovo OCR e non li corregge automaticamente. Verificare la trascrizione prima della generazione.

## v0.3
- Trasporto virtuale senza media: Play/Pausa, loop, velocità, frame, IN/OUT, ancoraggi e anteprima.
- Clic singolo seleziona; doppio clic nell'elenco o sulla timeline cerca l'IN e centra la timeline.
- La selezione aggiorna solo il pannello e le due righe interessate; canvas a larghezza viewport e palette precalcolata. Rimossa la limitazione a 32.000 pixel della timeline.
- Compatibile con progetti JSON v2. Test motore: `node test.mjs`.

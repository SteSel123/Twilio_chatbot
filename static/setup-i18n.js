/** Setup page i18n — same locales as landing (appassist-locale). */
(function (global) {
  const STORAGE_KEY = 'appassist-locale';

  const LOCALES = [
    { code: 'nl', label: 'NL' },
    { code: 'en', label: 'EN' },
    { code: 'fr', label: 'FR' },
    { code: 'es', label: 'ES' },
    { code: 'it', label: 'IT' },
    { code: 'de', label: 'DE' },
  ];

  const MESSAGES = {
    nl: {
      nav: {
        assistant: 'Assistent',
        features: 'Mogelijkheden',
        pricing: 'Tarieven',
        faq: 'Vragen',
        bookDemo: 'Plan gratis demo',
        openMenu: 'Menu openen',
        closeMenu: 'Menu sluiten',
      },
      setup: {
        metaTitle: 'Setup — AppAssist',
        pageTitle: 'Stel je WhatsApp-assistent in',
        pageSub:
          'Vijf stappen: openingstijden, upload, afspraak, herinnering, Google review.',
        docTitle: 'Stap 2 — Intern document',
        docSub:
          'Upload een tariefkaart, handleiding of protocol. In het gesprek zie je het groene paneel: zo raadpleegt de assistent jouw privé-document — klanten zien dat nooit.',
        uploadCta: 'Tik om bestand te kiezen',
        uploadHint: 'JPG, PNG, WebP of PDF · max 8 MB',
        privacy: 'je document wordt opgeslagen in jouw kennisbank voor deze assistent.',
        visionOff: 'Upload niet beschikbaar — alleen het openingsuren-voorbeeld wordt geladen.',
        previewLabel: 'Live voorbeeld',
        possibleClient: 'Mogelijke klant',
        online: 'online',
        loadingBusiness: 'Openingstijden laden…',
        loadingDoc: 'Document scannen…',
        loadingWait: 'Even geduld…',
        uploadProcessing: 'Document verwerkt — gesprek gaat verder…',
        chatLoading: 'Voorbeeld wordt geladen…',
        analyzingDoc: 'Document wordt geanalyseerd…',
        awaitUpload: 'Upload een document voor het volgende voorbeeld',
        awaitUploadSub: 'Tik hier · JPG, PNG, WebP of PDF',
        step1: 'Stap 1 — Openingstijden via Google',
        step2: 'Stap 2 — Intern document uploaden',
        step3: 'Stap 3 — Afspraak inplannen via e-mail',
        step4: 'Stap 4 — Automatische herinnering',
        step5: 'Stap 5 — Review op Google',
        internal: {
          docBadge: 'Intern · privé voor jouw team',
          webSearching: 'Web wordt geraadpleegd…',
          webDone: 'Info toegevoegd',
          calendarSearching: 'Agenda wordt geraadpleegd…',
          calendarDone: 'Afspraak ingepland',
          reminderSearching: 'Herinnering wordt ingepland…',
          reminderDone: 'Automatisch bericht verstuurd',
          reviewSearching: 'Google review-link wordt klaargezet…',
          reviewDone: 'Google review-link klaar',
          uploadScanning: 'Document scannen…',
          uploadScanDone: 'Document gelezen',
          proactiveBanner: 'Automatisch bericht',
        },
        progressLoading: 'WhatsApp-gesprek wordt geladen…',
        errorFileType: "Alleen foto's of PDF (JPG, PNG, WebP, PDF).",
        errorGeneric: 'Er ging iets mis.',
        errorPreview: 'Voorbeeld kon niet geladen worden.',
        errorUploadFirst: 'Wacht tot het openingsuren-voorbeeld klaar is.',
        errorUploadWait: 'Even geduld — het huidige voorbeeld speelt nog af.',
        errorUploadDone: 'Document is al geüpload — voorbeeld is compleet.',
      },
    },
    en: {
      nav: {
        assistant: 'Assistant',
        features: 'Features',
        pricing: 'Pricing',
        faq: 'FAQ',
        bookDemo: 'Book free demo',
        openMenu: 'Open menu',
        closeMenu: 'Close menu',
      },
      setup: {
        metaTitle: 'Setup — AppAssist',
        pageTitle: 'Set up your WhatsApp assistant',
        pageSub:
          'Five steps: opening hours, upload, appointment, reminder, Google review.',
        docTitle: 'Step 2 — Internal document',
        docSub:
          'Upload a rate card, manual or protocol. In the chat you will see the green panel: that is your private document being read — customers never see it.',
        uploadCta: 'Tap to choose a file',
        uploadHint: 'JPG, PNG, WebP or PDF · max 8 MB',
        privacy: 'your document is saved to your knowledge base for this assistant.',
        visionOff: 'Upload unavailable — only the opening-hours preview will load.',
        previewLabel: 'Live preview',
        possibleClient: 'Possible client',
        online: 'online',
        loadingBusiness: 'Loading opening hours…',
        loadingDoc: 'Scanning document…',
        loadingWait: 'One moment…',
        uploadProcessing: 'Processing document — continuing the chat…',
        chatLoading: 'Loading preview…',
        analyzingDoc: 'Analysing document…',
        awaitUpload: 'Upload a document for the next preview',
        awaitUploadSub: 'Tap here · JPG, PNG, WebP or PDF',
        step1: 'Step 1 — Opening hours via Google',
        step2: 'Step 2 — Upload internal document',
        step3: 'Step 3 — Book appointment via email',
        step4: 'Step 4 — Automatic reminder',
        step5: 'Step 5 — Google review',
        internal: {
          docBadge: 'Internal · private to your team',
          webSearching: 'Searching the web…',
          webDone: 'Info added',
          calendarSearching: 'Checking calendar…',
          calendarDone: 'Appointment booked',
          reminderSearching: 'Scheduling reminder…',
          reminderDone: 'Automatic message sent',
          reviewSearching: 'Preparing Google review link…',
          reviewDone: 'Google review link ready',
          uploadScanning: 'Scanning document…',
          uploadScanDone: 'Document read',
          proactiveBanner: 'Automatic message',
        },
        progressLoading: 'Loading WhatsApp conversation…',
        errorFileType: 'Images or PDF only (JPG, PNG, WebP, PDF).',
        errorGeneric: 'Something went wrong.',
        errorPreview: 'Could not load preview.',
        errorUploadFirst: 'Wait until the opening-hours preview is ready.',
        errorUploadWait: 'Please wait — the current preview is still playing.',
        errorUploadDone: 'Document already uploaded — preview is complete.',
      },
    },
    fr: {
      nav: {
        assistant: 'Assistant',
        features: 'Fonctionnalités',
        pricing: 'Tarifs',
        faq: 'FAQ',
        bookDemo: 'Réserver une démo gratuite',
        openMenu: 'Ouvrir le menu',
        closeMenu: 'Fermer le menu',
      },
      setup: {
        metaTitle: 'Configuration — AppAssist',
        pageTitle: 'Configurez votre assistant WhatsApp',
        pageSub:
          'Cinq étapes : horaires, document, rendez-vous, rappel, avis Google.',
        docTitle: 'Étape 2 — Document interne',
        docSub:
          'Téléversez une grille tarifaire, un manuel ou un protocole. Dans la conversation, le panneau vert montre la consultation de votre document privé — invisible pour vos clients.',
        uploadCta: 'Appuyez pour choisir un fichier',
        uploadHint: 'JPG, PNG, WebP ou PDF · max 8 Mo',
        privacy: 'votre document est enregistré dans votre base de connaissances pour cet assistant.',
        visionOff: 'Téléversement indisponible — seul l’aperçu des horaires se charge.',
        previewLabel: 'Aperçu en direct',
        possibleClient: 'Client potentiel',
        online: 'en ligne',
        loadingBusiness: 'Chargement des horaires…',
        loadingDoc: 'Analyse du document…',
        loadingWait: 'Un instant…',
        chatLoading: 'Chargement de l’aperçu…',
        analyzingDoc: 'Analyse du document…',
        awaitUpload: 'Téléversez un document pour la suite',
        awaitUploadSub: 'Appuyez ici · JPG, PNG, WebP ou PDF',
        step1: 'Étape 1 — Horaires via Google',
        step2: 'Étape 2 — Document interne',
        step3: 'Étape 3 — Rendez-vous par e-mail',
        step4: 'Étape 4 — Rappel automatique',
        step5: 'Étape 5 — Avis sur Google',
        internal: {
          docBadge: 'Interne · privé pour votre équipe',
          webSearching: 'Consultation du web…',
          webDone: 'Info ajoutée',
          calendarSearching: 'Consultation de l’agenda…',
          calendarDone: 'Rendez-vous planifié',
          reminderSearching: 'Planification du rappel…',
          reminderDone: 'Message automatique envoyé',
          reviewSearching: 'Préparation du lien d’avis Google…',
          reviewDone: 'Lien d’avis Google prêt',
          uploadScanning: 'Numérisation du document…',
          uploadScanDone: 'Document lu',
          proactiveBanner: 'Message automatique',
        },
        progressLoading: 'Chargement de la conversation…',
        errorFileType: 'Photos ou PDF uniquement (JPG, PNG, WebP, PDF).',
        errorGeneric: 'Une erreur est survenue.',
        errorPreview: 'Impossible de charger l’aperçu.',
        errorUploadFirst: 'Attendez la fin de l’aperçu des horaires.',
        errorUploadDone: 'Document déjà téléversé — aperçu terminé.',
      },
    },
    es: {
      nav: {
        assistant: 'Asistente',
        features: 'Funciones',
        pricing: 'Precios',
        faq: 'Preguntas',
        bookDemo: 'Reservar demo gratis',
        openMenu: 'Abrir menú',
        closeMenu: 'Cerrar menú',
      },
      setup: {
        metaTitle: 'Configuración — AppAssist',
        pageTitle: 'Configura tu asistente de WhatsApp',
        pageSub:
          'Cinco pasos: horario, documento, cita, recordatorio, reseña en Google.',
        docTitle: 'Paso 2 — Documento interno',
        docSub:
          'Sube una tarifa, manual o protocolo. En el chat verás el panel verde: ahí la asistente consulta tu documento privado — los clientes nunca lo ven.',
        uploadCta: 'Toca para elegir archivo',
        uploadHint: 'JPG, PNG, WebP o PDF · máx 8 MB',
        privacy: 'tu documento se guarda en tu base de conocimientos para este asistente.',
        visionOff: 'Subida no disponible — solo se carga el ejemplo de horario.',
        previewLabel: 'Vista previa en vivo',
        possibleClient: 'Cliente potencial',
        online: 'en línea',
        loadingBusiness: 'Cargando horario…',
        loadingDoc: 'Escaneando documento…',
        loadingWait: 'Un momento…',
        chatLoading: 'Cargando vista previa…',
        analyzingDoc: 'Analizando documento…',
        awaitUpload: 'Sube un documento para el siguiente ejemplo',
        awaitUploadSub: 'Toca aquí · JPG, PNG, WebP o PDF',
        step1: 'Paso 1 — Horario vía Google',
        step2: 'Paso 2 — Documento interno',
        step3: 'Paso 3 — Cita por correo',
        step4: 'Paso 4 — Recordatorio automático',
        step5: 'Paso 5 — Reseña en Google',
        internal: {
          docBadge: 'Interno · privado para tu equipo',
          webSearching: 'Consultando la web…',
          webDone: 'Info añadida',
          calendarSearching: 'Consultando agenda…',
          calendarDone: 'Cita reservada',
          reminderSearching: 'Programando recordatorio…',
          reminderDone: 'Mensaje automático enviado',
          reviewSearching: 'Preparando enlace de reseña…',
          reviewDone: 'Enlace de reseña listo',
          uploadScanning: 'Escaneando documento…',
          uploadScanDone: 'Documento leído',
          proactiveBanner: 'Mensaje automático',
        },
        progressLoading: 'Cargando conversación…',
        errorFileType: 'Solo fotos o PDF (JPG, PNG, WebP, PDF).',
        errorGeneric: 'Algo salió mal.',
        errorPreview: 'No se pudo cargar la vista previa.',
        errorUploadFirst: 'Espera a que termine el ejemplo de horario.',
        errorUploadDone: 'Documento ya subido — vista previa completa.',
      },
    },
    it: {
      nav: {
        assistant: 'Assistente',
        features: 'Funzionalità',
        pricing: 'Prezzi',
        faq: 'FAQ',
        bookDemo: 'Prenota demo gratuita',
        openMenu: 'Apri menu',
        closeMenu: 'Chiudi menu',
      },
      setup: {
        metaTitle: 'Setup — AppAssist',
        pageTitle: 'Configura il tuo assistente WhatsApp',
        pageSub:
          'Cinque passaggi: orari, documento, appuntamento, promemoria, recensione Google.',
        docTitle: 'Passaggio 2 — Documento interno',
        docSub:
          'Carica un listino, manuale o protocollo. Nella chat vedrai il pannello verde: lì l’assistente consulta il tuo documento privato — i clienti non lo vedono mai.',
        uploadCta: 'Tocca per scegliere un file',
        uploadHint: 'JPG, PNG, WebP o PDF · max 8 MB',
        privacy: 'il tuo documento viene salvato nella knowledge base per questo assistente.',
        visionOff: 'Upload non disponibile — viene caricata solo l’anteprima degli orari.',
        previewLabel: 'Anteprima live',
        possibleClient: 'Cliente potenziale',
        online: 'online',
        loadingBusiness: 'Caricamento orari…',
        loadingDoc: 'Scansione documento…',
        loadingWait: 'Un attimo…',
        chatLoading: 'Caricamento anteprima…',
        analyzingDoc: 'Analisi documento…',
        awaitUpload: 'Carica un documento per il prossimo esempio',
        awaitUploadSub: 'Tocca qui · JPG, PNG, WebP o PDF',
        step1: 'Passaggio 1 — Orari via Google',
        step2: 'Passaggio 2 — Documento interno',
        step3: 'Passaggio 3 — Appuntamento via e-mail',
        step4: 'Passaggio 4 — Promemoria automatico',
        step5: 'Passaggio 5 — Recensione Google',
        internal: {
          docBadge: 'Interno · privato per il tuo team',
          webSearching: 'Consultazione web…',
          webDone: 'Info aggiunta',
          calendarSearching: 'Consultazione agenda…',
          calendarDone: 'Appuntamento prenotato',
          reminderSearching: 'Programmazione promemoria…',
          reminderDone: 'Messaggio automatico inviato',
          reviewSearching: 'Preparazione link recensione…',
          reviewDone: 'Link recensione pronto',
          uploadScanning: 'Scansione documento…',
          uploadScanDone: 'Documento letto',
          proactiveBanner: 'Messaggio automatico',
        },
        progressLoading: 'Caricamento conversazione…',
        errorFileType: 'Solo foto o PDF (JPG, PNG, WebP, PDF).',
        errorGeneric: 'Qualcosa è andato storto.',
        errorPreview: 'Impossibile caricare l’anteprima.',
        errorUploadFirst: 'Attendi il completamento dell’anteprima orari.',
        errorUploadDone: 'Documento già caricato — anteprima completa.',
      },
    },
    de: {
      nav: {
        assistant: 'Assistent',
        features: 'Funktionen',
        pricing: 'Preise',
        faq: 'FAQ',
        bookDemo: 'Kostenlose Demo buchen',
        openMenu: 'Menü öffnen',
        closeMenu: 'Menü schließen',
      },
      setup: {
        metaTitle: 'Setup — AppAssist',
        pageTitle: 'WhatsApp-Assistent einrichten',
        pageSub:
          'Fünf Schritte: Öffnungszeiten, Upload, Termin, Erinnerung, Google-Bewertung.',
        docTitle: 'Schritt 2 — Internes Dokument',
        docSub:
          'Laden Sie eine Tarifkarte, ein Handbuch oder Protokoll hoch. Im Chat sehen Sie das grüne Panel: so liest der Assistent Ihr privates Dokument — Kunden sehen das nie.',
        uploadCta: 'Tippen, um Datei zu wählen',
        uploadHint: 'JPG, PNG, WebP oder PDF · max 8 MB',
        privacy: 'Ihr Dokument wird in Ihrer Wissensdatenbank für diesen Assistenten gespeichert.',
        visionOff: 'Upload nicht verfügbar — nur die Öffnungszeiten-Vorschau wird geladen.',
        previewLabel: 'Live-Vorschau',
        possibleClient: 'Möglicher Kunde',
        online: 'online',
        loadingBusiness: 'Öffnungszeiten werden geladen…',
        loadingDoc: 'Dokument wird gescannt…',
        loadingWait: 'Einen Moment…',
        chatLoading: 'Vorschau wird geladen…',
        analyzingDoc: 'Dokument wird analysiert…',
        awaitUpload: 'Laden Sie ein Dokument für das nächste Beispiel hoch',
        awaitUploadSub: 'Hier tippen · JPG, PNG, WebP oder PDF',
        step1: 'Schritt 1 — Öffnungszeiten via Google',
        step2: 'Schritt 2 — Internes Dokument hochladen',
        step3: 'Schritt 3 — Termin per E-Mail',
        step4: 'Schritt 4 — Automatische Erinnerung',
        step5: 'Schritt 5 — Google-Bewertung',
        internal: {
          docBadge: 'Intern · privat für Ihr Team',
          webSearching: 'Web wird durchsucht…',
          webDone: 'Info hinzugefügt',
          calendarSearching: 'Kalender wird abgerufen…',
          calendarDone: 'Termin gebucht',
          reminderSearching: 'Erinnerung wird geplant…',
          reminderDone: 'Automatische Nachricht gesendet',
          reviewSearching: 'Google-Bewertungslink wird vorbereitet…',
          reviewDone: 'Google-Bewertungslink bereit',
          uploadScanning: 'Dokument wird gescannt…',
          uploadScanDone: 'Dokument gelesen',
          proactiveBanner: 'Automatische Nachricht',
        },
        progressLoading: 'WhatsApp-Gespräch wird geladen…',
        errorFileType: 'Nur Fotos oder PDF (JPG, PNG, WebP, PDF).',
        errorGeneric: 'Etwas ist schiefgelaufen.',
        errorPreview: 'Vorschau konnte nicht geladen werden.',
        errorUploadFirst: 'Warten Sie, bis die Öffnungszeiten-Vorschau fertig ist.',
        errorUploadDone: 'Dokument bereits hochgeladen — Vorschau abgeschlossen.',
      },
    },
  };

  const INDUSTRY_SLUGS = ['industrial', 'construction', 'logistics', 'financial', 'property'];

  const INDUSTRY_DOC_SUB = {
    industrial: {
      nl: 'Handleiding, tariefkaart of storingsprotocol — upload optioneel om te zien hoe de assistent je document gebruikt.',
      en: 'Manual, rate card or breakdown protocol — optionally upload to see how the assistant uses your document.',
      fr: 'Manuel, grille tarifaire ou protocole de dépannage — téléversez un fichier pour voir comment l’assistant l’utilise.',
      es: 'Manual, tarifas o protocolo de averías — sube un archivo para ver cómo lo usa el asistente.',
      it: 'Manuale, listino o protocollo di intervento — carica un file per vedere come l’assistente lo usa.',
      de: 'Handbuch, Tarifkarte oder Störungsprotokoll — optional hochladen, um zu sehen, wie der Assistent Ihr Dokument nutzt.',
    },
    construction: {
      nl: 'Prijslijst, installatieprotocol of garantievoorwaarden — upload optioneel voor een live voorbeeld.',
      en: 'Price list, install protocol or warranty terms — optionally upload for a live preview.',
      fr: 'Grille tarifaire, protocole d’installation ou garanties — téléversez pour un aperçu en direct.',
      es: 'Lista de precios, protocolo de instalación o garantías — sube un archivo para la vista previa.',
      it: 'Listino, protocollo di installazione o garanzie — carica un file per l’anteprima live.',
      de: 'Preisliste, Installationsprotokoll oder Garantie — optional hochladen für die Live-Vorschau.',
    },
    logistics: {
      nl: 'Transporttarieven, SLA of track & trace-info — upload optioneel om het voorbeeld te verrijken.',
      en: 'Transport rates, SLA or track & trace info — optionally upload to enrich the preview.',
      fr: 'Tarifs transport, SLA ou suivi — téléversez pour enrichir l’aperçu.',
      es: 'Tarifas de transporte, SLA o seguimiento — sube un archivo para enriquecer la vista previa.',
      it: 'Tariffe trasporto, SLA o tracking — carica un file per arricchire l’anteprima.',
      de: 'Transporttarife, SLA oder Tracking-Info — optional hochladen für die Vorschau.',
    },
    financial: {
      nl: 'Dienstenoverzicht, tarieven of schadechecklist — upload optioneel voor het live voorbeeld.',
      en: 'Service overview, fee schedule or claims checklist — optionally upload for the live preview.',
      fr: 'Catalogue de services, tarifs ou checklist sinistre — téléversez pour l’aperçu en direct.',
      es: 'Catálogo de servicios, tarifas o checklist de siniestros — sube un archivo para la vista previa.',
      it: 'Panoramica servizi, tariffe o checklist sinistri — carica un file per l’anteprima live.',
      de: 'Leistungsübersicht, Honorare oder Schaden-Checkliste — optional hochladen für die Vorschau.',
    },
    property: {
      nl: 'Beheerhandboek, meldingenprotocol of technische partners — upload optioneel voor het voorbeeld.',
      en: 'Management handbook, incident protocol or technical partners — optionally upload for the preview.',
      fr: 'Manuel de gestion, protocole d’incidents ou partenaires techniques — téléversez pour l’aperçu.',
      es: 'Manual de gestión, protocolo de incidencias o partners técnicos — sube un archivo para la vista previa.',
      it: 'Manuale di gestione, protocollo guasti o partner tecnici — carica un file per l’anteprima.',
      de: 'Verwaltungshandbuch, Meldeprotokoll oder Technikpartner — optional hochladen für die Vorschau.',
    },
  };

  function normalizeIndustry(raw) {
    const key = String(raw || 'industrial').toLowerCase();
    const alias = { general: 'industrial', services: 'industrial', other: 'industrial' };
    const slug = alias[key] || key;
    return INDUSTRY_SLUGS.includes(slug) ? slug : 'industrial';
  }

  function detectLocale() {
    const params = new URLSearchParams(window.location.search);
    const fromUrl = (params.get('locale') || '').slice(0, 2).toLowerCase();
    if (fromUrl && MESSAGES[fromUrl]) {
      localStorage.setItem(STORAGE_KEY, fromUrl);
      return fromUrl;
    }
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && MESSAGES[stored]) return stored;
    const browser = (navigator.language || 'nl').slice(0, 2).toLowerCase();
    return MESSAGES[browser] ? browser : 'nl';
  }

  function t(locale, key) {
    const parts = key.split('.');
    let node = MESSAGES[locale] || MESSAGES.nl;
    for (const p of parts) {
      node = node?.[p];
    }
    return node || key;
  }

  function applyTranslations(locale) {
    document.documentElement.lang = locale;
    const industry = normalizeIndustry(document.documentElement.getAttribute('data-industry'));
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.getAttribute('data-i18n');
      if (key === 'setup.docSub') {
        const industrySubs = INDUSTRY_DOC_SUB[industry] || INDUSTRY_DOC_SUB.industrial;
        el.textContent = industrySubs[locale] || industrySubs.en || t(locale, key);
        return;
      }
      const val = t(locale, key);
      if (val) el.textContent = val;
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
      const key = el.getAttribute('data-i18n-placeholder');
      const val = t(locale, key);
      if (val) el.setAttribute('placeholder', val);
    });
    const titleEl = document.querySelector('title');
    if (titleEl) {
      const biz = titleEl.getAttribute('data-business') || 'AppAssist';
      titleEl.textContent = t(locale, 'setup.metaTitle').replace('AppAssist', biz) || titleEl.textContent;
    }
    document.querySelectorAll('[data-locale-btn]').forEach((btn) => {
      const code = btn.getAttribute('data-locale-btn');
      btn.classList.toggle('active', code === locale);
    });
  }

  function initSetupI18n(landingUrl, onLocaleChange) {
    let locale = detectLocale();

    function setLocale(code) {
      if (!MESSAGES[code]) return;
      locale = code;
      localStorage.setItem(STORAGE_KEY, code);
      applyTranslations(locale);
      if (typeof onLocaleChange === 'function') onLocaleChange(locale, MESSAGES[locale]);
    }

    const navRoot = document.getElementById('site-nav');
    document.querySelectorAll('[data-locale-btn]').forEach((btn) => {
      btn.addEventListener('click', () => setLocale(btn.getAttribute('data-locale-btn')));
    });
    if (navRoot) {
      const menuBtn = document.getElementById('nav-menu-btn');
      const menuClose = document.getElementById('nav-menu-close');
      const mobilePanel = document.getElementById('nav-mobile-panel');
      const mobileBackdrop = document.getElementById('nav-mobile-backdrop');
      function closeMobile() {
        mobilePanel?.classList.remove('open');
        mobileBackdrop?.classList.remove('open');
        document.body.classList.remove('nav-open');
      }
      menuBtn?.addEventListener('click', () => {
        mobilePanel?.classList.add('open');
        mobileBackdrop?.classList.add('open');
        document.body.classList.add('nav-open');
      });
      menuClose?.addEventListener('click', closeMobile);
      mobileBackdrop?.addEventListener('click', closeMobile);
      document.querySelectorAll('.nav-mobile-link').forEach((a) => {
        a.addEventListener('click', closeMobile);
      });
    }
    const base = (landingUrl || '').replace(/\/$/, '');
    document.querySelectorAll('[data-landing-href]').forEach((a) => {
      const hash = a.getAttribute('data-landing-href') || '';
      a.href = base + hash;
    });
    const logo = document.getElementById('nav-logo-link');
    if (logo) logo.href = base || '#';

    applyTranslations(locale);
    return { getLocale: () => locale, setLocale, t: (key) => t(locale, key), LOCALES };
  }

  global.SetupI18n = { initSetupI18n, LOCALES, MESSAGES };
})(window);

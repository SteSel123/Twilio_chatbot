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
          'We zoeken je bedrijf automatisch op via Google. Optioneel kun je een document uploaden.',
        docTitle: 'Intern document (optioneel)',
        docSub:
          'Menu, prijslijst of openingstijden — upload optioneel om te zien hoe de assistent je document gebruikt.',
        uploadCta: 'Tik om bestand te kiezen',
        uploadHint: 'JPG, PNG, WebP of PDF · max 8 MB',
        privacy:
          'Privacy: je bestand wordt alleen tijdelijk gelezen voor dit voorbeeld en niet opgeslagen aan onze kant.',
        visionOff: 'Upload niet beschikbaar — het Google-voorbeeld wordt wel geladen.',
        previewLabel: 'Live voorbeeld',
        possibleClient: 'Mogelijke klant',
        online: 'online',
        loadingBusiness: 'Bedrijfsinfo laden…',
        loadingDoc: 'Document scannen…',
        loadingWait: 'Even geduld…',
        chatLoading: 'Voorbeeld wordt geladen…',
        analyzingDoc: 'Document wordt geanalyseerd…',
        progressLoading: 'WhatsApp-gesprek wordt geladen…',
        errorFileType: "Alleen foto's of PDF (JPG, PNG, WebP, PDF).",
        errorGeneric: 'Er ging iets mis.',
        errorPreview: 'Voorbeeld kon niet geladen worden.',
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
          'We look up your business on Google automatically. Optionally upload a document.',
        docTitle: 'Internal document (optional)',
        docSub:
          'Menu, price list or hours — optionally upload to see how the assistant uses your document.',
        uploadCta: 'Tap to choose a file',
        uploadHint: 'JPG, PNG, WebP or PDF · max 8 MB',
        privacy:
          'Privacy: your file is only read temporarily for this preview and not stored on our side.',
        visionOff: 'Upload unavailable — the Google preview will still load.',
        previewLabel: 'Live preview',
        possibleClient: 'Possible client',
        online: 'online',
        loadingBusiness: 'Loading business info…',
        loadingDoc: 'Scanning document…',
        loadingWait: 'One moment…',
        chatLoading: 'Loading preview…',
        analyzingDoc: 'Analysing document…',
        progressLoading: 'Loading WhatsApp conversation…',
        errorFileType: 'Photos or PDF only (JPG, PNG, WebP, PDF).',
        errorGeneric: 'Something went wrong.',
        errorPreview: 'Preview could not be loaded.',
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
          'Nous recherchons votre entreprise sur Google. Vous pouvez aussi téléverser un document.',
        docTitle: 'Document interne (optionnel)',
        docSub:
          'Menu, tarifs ou horaires — téléversez un fichier pour voir comment l’assistant l’utilise.',
        uploadCta: 'Appuyez pour choisir un fichier',
        uploadHint: 'JPG, PNG, WebP ou PDF · max 8 Mo',
        privacy:
          'Confidentialité : votre fichier est lu temporairement pour cet aperçu et n’est pas stocké.',
        visionOff: 'Téléversement indisponible — l’aperçu Google se charge quand même.',
        previewLabel: 'Aperçu en direct',
        possibleClient: 'Client potentiel',
        online: 'en ligne',
        loadingBusiness: 'Chargement des infos…',
        loadingDoc: 'Analyse du document…',
        loadingWait: 'Un instant…',
        chatLoading: 'Chargement de l’aperçu…',
        analyzingDoc: 'Analyse du document…',
        progressLoading: 'Chargement de la conversation…',
        errorFileType: 'Photos ou PDF uniquement (JPG, PNG, WebP, PDF).',
        errorGeneric: 'Une erreur est survenue.',
        errorPreview: 'Impossible de charger l’aperçu.',
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
          'Buscamos tu negocio en Google automáticamente. Opcionalmente sube un documento.',
        docTitle: 'Documento interno (opcional)',
        docSub:
          'Menú, lista de precios u horarios — sube un archivo para ver cómo lo usa el asistente.',
        uploadCta: 'Toca para elegir archivo',
        uploadHint: 'JPG, PNG, WebP o PDF · máx 8 MB',
        privacy:
          'Privacidad: tu archivo solo se lee temporalmente para esta vista previa y no se guarda.',
        visionOff: 'Subida no disponible — la vista previa de Google sí se cargará.',
        previewLabel: 'Vista previa en vivo',
        possibleClient: 'Cliente potencial',
        online: 'en línea',
        loadingBusiness: 'Cargando información…',
        loadingDoc: 'Escaneando documento…',
        loadingWait: 'Un momento…',
        chatLoading: 'Cargando vista previa…',
        analyzingDoc: 'Analizando documento…',
        progressLoading: 'Cargando conversación…',
        errorFileType: 'Solo fotos o PDF (JPG, PNG, WebP, PDF).',
        errorGeneric: 'Algo salió mal.',
        errorPreview: 'No se pudo cargar la vista previa.',
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
          'Cerchiamo la tua attività su Google. Puoi anche caricare un documento.',
        docTitle: 'Documento interno (opzionale)',
        docSub:
          'Menu, listino o orari — carica un file per vedere come l’assistente lo usa.',
        uploadCta: 'Tocca per scegliere un file',
        uploadHint: 'JPG, PNG, WebP o PDF · max 8 MB',
        privacy:
          'Privacy: il file viene letto solo temporaneamente per questa anteprima e non viene salvato.',
        visionOff: 'Upload non disponibile — l’anteprima Google verrà comunque caricata.',
        previewLabel: 'Anteprima live',
        possibleClient: 'Cliente potenziale',
        online: 'online',
        loadingBusiness: 'Caricamento info…',
        loadingDoc: 'Scansione documento…',
        loadingWait: 'Un attimo…',
        chatLoading: 'Caricamento anteprima…',
        analyzingDoc: 'Analisi documento…',
        progressLoading: 'Caricamento conversazione…',
        errorFileType: 'Solo foto o PDF (JPG, PNG, WebP, PDF).',
        errorGeneric: 'Qualcosa è andato storto.',
        errorPreview: 'Impossibile caricare l’anteprima.',
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
          'Wir suchen Ihr Unternehmen automatisch bei Google. Optional können Sie ein Dokument hochladen.',
        docTitle: 'Internes Dokument (optional)',
        docSub:
          'Menü, Preisliste oder Öffnungszeiten — optional hochladen, um zu sehen, wie der Assistent Ihr Dokument nutzt.',
        uploadCta: 'Tippen, um Datei zu wählen',
        uploadHint: 'JPG, PNG, WebP oder PDF · max 8 MB',
        privacy:
          'Datenschutz: Ihre Datei wird nur temporär für diese Vorschau gelesen und nicht gespeichert.',
        visionOff: 'Upload nicht verfügbar — die Google-Vorschau wird trotzdem geladen.',
        previewLabel: 'Live-Vorschau',
        possibleClient: 'Möglicher Kunde',
        online: 'online',
        loadingBusiness: 'Unternehmensinfo wird geladen…',
        loadingDoc: 'Dokument wird gescannt…',
        loadingWait: 'Einen Moment…',
        chatLoading: 'Vorschau wird geladen…',
        analyzingDoc: 'Dokument wird analysiert…',
        progressLoading: 'WhatsApp-Gespräch wird geladen…',
        errorFileType: 'Nur Fotos oder PDF (JPG, PNG, WebP, PDF).',
        errorGeneric: 'Etwas ist schiefgelaufen.',
        errorPreview: 'Vorschau konnte nicht geladen werden.',
      },
    },
  };

  function detectLocale() {
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
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.getAttribute('data-i18n');
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

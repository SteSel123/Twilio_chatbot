"""Setup preview copy — nl, en, fr, es, it, de."""

from __future__ import annotations

import re

LOCALES = frozenset({"nl", "en", "fr", "es", "it", "de"})

_WEEKDAYS = {
    "nl": ("maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"),
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "fr": ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"),
    "es": ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"),
    "it": ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"),
    "de": ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"),
}

_MONTHS = {
    "nl": (
        "januari", "februari", "maart", "april", "mei", "juni",
        "juli", "augustus", "september", "oktober", "november", "december",
    ),
    "en": (
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ),
    "fr": (
        "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    ),
    "es": (
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ),
    "it": (
        "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
        "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
    ),
    "de": (
        "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember",
    ),
}

_STRINGS: dict[str, dict[str, str]] = {
    "opening_hours_question": {
        "nl": "Hoe laat zijn jullie vandaag open?",
        "en": "What are your opening hours today?",
        "fr": "Quels sont vos horaires aujourd'hui ?",
        "es": "¿Cuál es vuestro horario hoy?",
        "it": "Quali sono i vostri orari oggi?",
        "de": "Wie sind Ihre Öffnungszeiten heute?",
    },
    "maps_trace_searching": {
        "nl": "Google Maps wordt geraadpleegd…",
        "en": "Checking Google Maps…",
        "fr": "Consultation de Google Maps…",
        "es": "Consultando Google Maps…",
        "it": "Consultazione di Google Maps…",
        "de": "Google Maps wird abgerufen…",
    },
    "maps_trace_done": {
        "nl": "Openingstijden opgehaald",
        "en": "Opening hours retrieved",
        "fr": "Horaires récupérés",
        "es": "Horario obtenido",
        "it": "Orari recuperati",
        "de": "Öffnungszeiten abgerufen",
    },
    "maps_trace_note": {
        "nl": "Publieke bron — geen geüploade documenten van de ondernemer.",
        "en": "Public source — no documents uploaded by the business.",
        "fr": "Source publique — aucun document téléversé par l'entreprise.",
        "es": "Fuente pública — sin documentos subidos por el negocio.",
        "it": "Fonte pubblica — nessun documento caricato dall'azienda.",
        "de": "Öffentliche Quelle — keine hochgeladenen Dokumente des Unternehmens.",
    },
    "business_trace_searching": {
        "nl": "Bedrijfsgegevens ophalen…",
        "en": "Fetching business details…",
        "fr": "Récupération des infos entreprise…",
        "es": "Obteniendo datos del negocio…",
        "it": "Recupero dati aziendali…",
        "de": "Unternehmensdaten werden geladen…",
    },
    "business_trace_done": {
        "nl": "Openingstijden & contact gevonden",
        "en": "Hours & contact found",
        "fr": "Horaires et contact trouvés",
        "es": "Horario y contacto encontrados",
        "it": "Orari e contatti trovati",
        "de": "Öffnungszeiten & Kontakt gefunden",
    },
    "business_trace_note": {
        "nl": "Publieke info via Google — geen documenten van jou geüpload.",
        "en": "Public info via Google — no documents uploaded by you.",
        "fr": "Infos publiques via Google — aucun document téléversé par vous.",
        "es": "Info pública vía Google — sin documentos subidos por ti.",
        "it": "Info pubbliche via Google — nessun documento caricato da te.",
        "de": "Öffentliche Infos via Google — keine von Ihnen hochgeladenen Dokumente.",
    },
    "upload_trace_searching": {
        "nl": "Intern document wordt geraadpleegd…",
        "en": "Reading internal document…",
        "fr": "Consultation du document interne…",
        "es": "Consultando documento interno…",
        "it": "Consultazione documento interno…",
        "de": "Internes Dokument wird gelesen…",
    },
    "upload_trace_done": {
        "nl": "Intern document gelezen",
        "en": "Internal document read",
        "fr": "Document interne lu",
        "es": "Documento interno leído",
        "it": "Documento interno letto",
        "de": "Internes Dokument gelesen",
    },
    "upload_trace_note": {
        "nl": "Privé voor jouw team — klanten zien dit paneel en je bestand nooit.",
        "en": "Private to your team — customers never see this panel or your file.",
        "fr": "Privé pour votre équipe — vos clients ne voient jamais ce panneau ni votre fichier.",
        "es": "Privado para tu equipo — los clientes nunca ven este panel ni tu archivo.",
        "it": "Privato per il tuo team — i clienti non vedono mai questo pannello né il file.",
        "de": "Privat für Ihr Team — Kunden sehen dieses Panel und Ihre Datei nie.",
    },
    "upload_reply_solar": {
        "nl": "Hoi! Volgens onze prijslijst kost een installatie met {item} {price} (materiaal + installatie). Zal ik een vrijblijvende offerte op maat voor je uitwerken?",
        "en": "Hi! According to our price list, an installation with {item} costs {price} (materials + installation). Shall I prepare a no-obligation quote for you?",
        "fr": "Bonjour ! D'après notre grille tarifaire, une installation avec {item} coûte {price} (matériel + pose). Je prépare un devis gratuit pour vous ?",
        "es": "¡Hola! Según nuestra lista de precios, una instalación con {item} cuesta {price} (material + instalación). ¿Preparo un presupuesto sin compromiso?",
        "it": "Ciao! Secondo il nostro listino, un'installazione con {item} costa {price} (materiali + installazione). Preparo un preventivo gratuito?",
        "de": "Hallo! Laut unserer Preisliste kostet eine Installation mit {item} {price} (Material + Montage). Soll ich ein unverbindliches Angebot erstellen?",
    },
    "upload_reply_priced": {
        "nl": "Hoi! {item} kost {price} bij ons. Zal ik de details voor je uitwerken?",
        "en": "Hi! {item} costs {price} with us. Shall I work out the details for you?",
        "fr": "Bonjour ! {item} coûte {price} chez nous. Je vous détaille cela ?",
        "es": "¡Hola! {item} cuesta {price} con nosotros. ¿Te preparo los detalles?",
        "it": "Ciao! {item} costa {price} da noi. Ti preparo i dettagli?",
        "de": "Hallo! {item} kostet bei uns {price}. Soll ich die Details ausarbeiten?",
    },
    "upload_q_solar": {
        "nl": "Hoi! Wat kost een installatie met {item} bij {name}?",
        "en": "Hi! What does an installation with {item} cost at {name}?",
        "fr": "Bonjour ! Combien coûte une installation avec {item} chez {name} ?",
        "es": "¡Hola! ¿Cuánto cuesta una instalación con {item} en {name}?",
        "it": "Ciao! Quanto costa un'installazione con {item} da {name}?",
        "de": "Hallo! Was kostet eine Installation mit {item} bei {name}?",
    },
    "upload_q_priced": {
        "nl": "Hoi! Wat kost {item} bij {name}?",
        "en": "Hi! What does {item} cost at {name}?",
        "fr": "Bonjour ! Combien coûte {item} chez {name} ?",
        "es": "¡Hola! ¿Cuánto cuesta {item} en {name}?",
        "it": "Ciao! Quanto costa {item} da {name}?",
        "de": "Hallo! Was kostet {item} bei {name}?",
    },
    "upload_q_topic": {
        "nl": "Hoi! Kunnen jullie me iets vertellen over {topic}?",
        "en": "Hi! Can you tell me more about {topic}?",
        "fr": "Bonjour ! Pouvez-vous m'en dire plus sur {topic} ?",
        "es": "¡Hola! ¿Podéis contarme más sobre {topic}?",
        "it": "Ciao! Potete dirmi di più su {topic}?",
        "de": "Hallo! Können Sie mir mehr über {topic} erzählen?",
    },
    "upload_q_document": {
        "nl": "Hoi! Ik las jullie document over {stem} — kunnen jullie de prijzen en voorwaarden toelichten?",
        "en": "Hi! I read your document about {stem} — can you explain the prices and terms?",
        "fr": "Bonjour ! J'ai lu votre document sur {stem} — pouvez-vous expliquer les tarifs et conditions ?",
        "es": "¡Hola! Leí vuestro documento sobre {stem} — ¿podéis explicar precios y condiciones?",
        "it": "Ciao! Ho letto il vostro documento su {stem} — potete spiegare prezzi e condizioni?",
        "de": "Hallo! Ich habe Ihr Dokument über {stem} gelesen — können Sie Preise und Bedingungen erläutern?",
    },
    "upload_q_fallback": {
        "nl": "Hoi! Kunnen jullie me iets vertellen over de tarieven in jullie document, {name}?",
        "en": "Hi! Can you tell me about the rates in your document, {name}?",
        "fr": "Bonjour ! Pouvez-vous m'expliquer les tarifs de votre document, {name} ?",
        "es": "¡Hola! ¿Podéis explicarme las tarifas de vuestro documento, {name}?",
        "it": "Ciao! Potete spiegarmi le tariffe del vostro documento, {name}?",
        "de": "Hallo! Können Sie mir die Tarife in Ihrem Dokument erklären, {name}?",
    },
    "solar_panel_count": {
        "nl": "{count} zonnepanelen",
        "en": "{count} solar panels",
        "fr": "{count} panneaux solaires",
        "es": "{count} paneles solares",
        "it": "{count} pannelli solari",
        "de": "{count} Solarmodule",
    },
    "service_solar_installation": {
        "nl": "de installatie ({item})",
        "en": "the installation ({item})",
        "fr": "l'installation ({item})",
        "es": "la instalación ({item})",
        "it": "l'installazione ({item})",
        "de": "die Installation ({item})",
    },
    "upload_stem_solar": {
        "nl": "zonnepanelen",
        "en": "solar panels",
        "fr": "panneaux solaires",
        "es": "paneles solares",
        "it": "pannelli solari",
        "de": "Solarmodule",
    },
    "calendar_q1": {
        "nl": "Hoi! Kunnen we {date} een afspraak inplannen voor {service}?",
        "en": "Hi! Can we schedule an appointment on {date} for {service}?",
        "fr": "Bonjour ! Pouvons-nous planifier un rendez-vous {date} pour {service} ?",
        "es": "¡Hola! ¿Podemos agendar una cita el {date} para {service}?",
        "it": "Ciao! Possiamo fissare un appuntamento {date} per {service}?",
        "de": "Hallo! Können wir am {date} einen Termin für {service} planen?",
    },
    "calendar_r1": {
        "nl": "Hoi! {date} om {slot} past goed voor {service}. Wat is je e-mailadres? Dan stuur ik je meteen een agenda-uitnodiging.",
        "en": "Hi! {date} at {slot} works well for {service}. What's your email address? I'll send you a calendar invite right away.",
        "fr": "Bonjour ! {date} à {slot} convient pour {service}. Quelle est votre adresse e-mail ? J'envoie tout de suite une invitation.",
        "es": "¡Hola! {date} a las {slot} encaja para {service}. ¿Cuál es tu correo? Te envío la invitación al instante.",
        "it": "Ciao! {date} alle {slot} va bene per {service}. Qual è la tua e-mail? Ti mando subito l'invito.",
        "de": "Hallo! {date} um {slot} passt für {service}. Wie lautet Ihre E-Mail? Ich sende sofort eine Kalendereinladung.",
    },
    "calendar_q2": {
        "nl": "Mijn e-mail is {email}",
        "en": "My email is {email}",
        "fr": "Mon e-mail est {email}",
        "es": "Mi correo es {email}",
        "it": "La mia e-mail è {email}",
        "de": "Meine E-Mail ist {email}",
    },
    "calendar_r2": {
        "nl": "Top! Je ontvangt een agenda-uitnodiging op {email} voor {date} om {slot} — {service}.",
        "en": "Great! You'll receive a calendar invite at {email} for {date} at {slot} — {service}.",
        "fr": "Parfait ! Vous recevrez une invitation sur {email} pour {date} à {slot} — {service}.",
        "es": "¡Genial! Recibirás una invitación en {email} para {date} a las {slot} — {service}.",
        "it": "Perfetto! Riceverai un invito su {email} per {date} alle {slot} — {service}.",
        "de": "Super! Sie erhalten eine Einladung an {email} für {date} um {slot} — {service}.",
    },
    "calendar_r2_fallback": {
        "nl": "Dank je! Je ontvangt een agenda-uitnodiging op {email} voor {date} om {slot}.",
        "en": "Thanks! You'll receive a calendar invite at {email} for {date} at {slot}.",
        "fr": "Merci ! Vous recevrez une invitation sur {email} pour {date} à {slot}.",
        "es": "¡Gracias! Recibirás una invitación en {email} para {date} a las {slot}.",
        "it": "Grazie! Riceverai un invito su {email} per {date} alle {slot}.",
        "de": "Danke! Sie erhalten eine Einladung an {email} für {date} um {slot}.",
    },
    "calendar_trace_searching": {
        "nl": "{provider} wordt geraadpleegd…",
        "en": "Checking {provider}…",
        "fr": "Consultation de {provider}…",
        "es": "Consultando {provider}…",
        "it": "Consultazione di {provider}…",
        "de": "{provider} wird abgerufen…",
    },
    "calendar_trace_invite_done": {
        "nl": "Uitnodiging verstuurd — {date} om {slot}",
        "en": "Invite sent — {date} at {slot}",
        "fr": "Invitation envoyée — {date} à {slot}",
        "es": "Invitación enviada — {date} a las {slot}",
        "it": "Invito inviato — {date} alle {slot}",
        "de": "Einladung gesendet — {date} um {slot}",
    },
    "calendar_trace_invite_note": {
        "nl": "Agenda-uitnodiging naar {email}.",
        "en": "Calendar invite sent to {email}.",
        "fr": "Invitation envoyée à {email}.",
        "es": "Invitación enviada a {email}.",
        "it": "Invito inviato a {email}.",
        "de": "Kalendereinladung an {email}.",
    },
    "tag_appointment": {
        "nl": "Afspraak / planning",
        "en": "Appointment / scheduling",
        "fr": "Rendez-vous / planning",
        "es": "Cita / planificación",
        "it": "Appuntamento / pianificazione",
        "de": "Termin / Planung",
    },
    "tag_invite_sent": {
        "nl": "Uitnodiging verstuurd",
        "en": "Invite sent",
        "fr": "Invitation envoyée",
        "es": "Invitación enviada",
        "it": "Invito inviato",
        "de": "Einladung gesendet",
    },
    "reminder_message": {
        "nl": "Hoi {name}! Even een herinnering: je hebt om {slot} een afspraak bij {business} voor {service}. Tot straks!",
        "en": "Hi {name}! Just a reminder: you have an appointment at {slot} with {business} for {service}. See you soon!",
        "fr": "Bonjour {name} ! Petit rappel : vous avez rendez-vous à {slot} chez {business} pour {service}. À tout à l'heure !",
        "es": "¡Hola {name}! Un recordatorio: tienes cita a las {slot} con {business} para {service}. ¡Hasta pronto!",
        "it": "Ciao {name}! Promemoria: hai un appuntamento alle {slot} con {business} per {service}. A presto!",
        "de": "Hallo {name}! Kurze Erinnerung: Sie haben um {slot} einen Termin bei {business} für {service}. Bis gleich!",
    },
    "reminder_trace_searching": {
        "nl": "Herinnering wordt ingepland…",
        "en": "Scheduling reminder…",
        "fr": "Planification du rappel…",
        "es": "Programando recordatorio…",
        "it": "Programmazione promemoria…",
        "de": "Erinnerung wird geplant…",
    },
    "reminder_trace_done": {
        "nl": "Automatisch bericht verstuurd",
        "en": "Automatic message sent",
        "fr": "Message automatique envoyé",
        "es": "Mensaje automático enviado",
        "it": "Messaggio automatico inviato",
        "de": "Automatische Nachricht gesendet",
    },
    "reminder_trace_note": {
        "nl": "Proactief via WhatsApp — klant hoeft niets te sturen.",
        "en": "Proactive via WhatsApp — customer doesn't need to send anything.",
        "fr": "Proactif via WhatsApp — le client n'a rien à envoyer.",
        "es": "Proactivo por WhatsApp — el cliente no tiene que enviar nada.",
        "it": "Proattivo via WhatsApp — il cliente non deve inviare nulla.",
        "de": "Proaktiv via WhatsApp — Kunde muss nichts senden.",
    },
    "proactive_banner": {
        "nl": "Automatisch bericht",
        "en": "Automatic message",
        "fr": "Message automatique",
        "es": "Mensaje automático",
        "it": "Messaggio automatico",
        "de": "Automatische Nachricht",
    },
    "tag_reminder": {
        "nl": "Herinnering afspraak",
        "en": "Appointment reminder",
        "fr": "Rappel de rendez-vous",
        "es": "Recordatorio de cita",
        "it": "Promemoria appuntamento",
        "de": "Terminerinnerung",
    },
    "review_service_fallback": {
        "nl": "de werkzaamheden",
        "en": "the work",
        "fr": "les travaux",
        "es": "los trabajos",
        "it": "i lavori",
        "de": "die Arbeiten",
    },
    "review_followup_ask": {
        "nl": "Hoi {name}! Alles goed verlopen bij {business}? We horen graag of {service} naar wens was.",
        "en": "Hi {name}! Did everything go well at {business}? We'd love to know if {service} met your expectations.",
        "fr": "Bonjour {name} ! Tout s'est bien passé chez {business} ? Dites-nous si {service} vous convient.",
        "es": "¡Hola {name}! ¿Todo bien en {business}? Nos encantaría saber si {service} fue como esperabas.",
        "it": "Ciao {name}! È andato tutto bene con {business}? Ci fa piacere sapere se {service} è stato di tuo gradimento.",
        "de": "Hallo {name}! Ist bei {business} alles gut gelaufen? Wir freuen uns zu hören, ob {service} Ihren Wünschen entsprach.",
    },
    "review_question": {
        "nl": "Bedankt, alles is top verlopen!",
        "en": "Thanks, everything went great!",
        "fr": "Merci, tout s'est très bien passé !",
        "es": "¡Gracias, todo fue genial!",
        "it": "Grazie, è andato tutto benissimo!",
        "de": "Danke, alles lief super!",
    },
    "review_reply_intro": {
        "nl": "Wat fijn om te horen, {name}! Zou je ons een korte review willen geven op {platform}? Dat helpt {business} enorm — ⭐⭐⭐⭐⭐",
        "en": "Great to hear, {name}! Would you leave us a short review on {platform}? It helps {business} a lot — ⭐⭐⭐⭐⭐",
        "fr": "Ravi de l'entendre, {name} ! Pourriez-vous nous laisser un avis sur {platform} ? Cela aide énormément {business} — ⭐⭐⭐⭐⭐",
        "es": "¡Qué bien, {name}! ¿Nos dejarías una reseña en {platform}? Ayuda mucho a {business} — ⭐⭐⭐⭐⭐",
        "it": "Che bello, {name}! Ci lasci una recensione su {platform}? Aiuta molto {business} — ⭐⭐⭐⭐⭐",
        "de": "Schön zu hören, {name}! Würden Sie uns eine kurze Bewertung auf {platform} geben? Das hilft {business} sehr — ⭐⭐⭐⭐⭐",
    },
    "review_link_label": {
        "nl": "Google review",
        "en": "Google review",
        "fr": "Avis Google",
        "es": "Reseña en Google",
        "it": "Recensione Google",
        "de": "Google-Bewertung",
    },
    "review_link_detail": {
        "nl": "Tik om een review te schrijven voor {business}",
        "en": "Tap to write a review for {business}",
        "fr": "Appuyez pour laisser un avis pour {business}",
        "es": "Toca para escribir una reseña de {business}",
        "it": "Tocca per lasciare una recensione per {business}",
        "de": "Tippen, um eine Bewertung für {business} zu schreiben",
    },
    "review_customer_done": {
        "nl": "Review geplaatst! Bedankt en tot ziens!",
        "en": "Review posted! Thanks, goodbye!",
        "fr": "Avis publié ! Merci et au revoir !",
        "es": "¡Reseña publicada! ¡Gracias y hasta luego!",
        "it": "Recensione pubblicata! Grazie e arrivederci!",
        "de": "Bewertung abgegeben! Danke und auf Wiedersehen!",
    },
    "review_reply_with_link": {
        "nl": "Wat fijn om te horen, {name}! Zou je ons een korte review willen geven op {platform}? Dat helpt {business} enorm — ⭐⭐⭐⭐⭐\n\n{url}",
        "en": "Great to hear, {name}! Would you leave us a short review on {platform}? It helps {business} a lot — ⭐⭐⭐⭐⭐\n\n{url}",
        "fr": "Ravi de l'entendre, {name} ! Pourriez-vous nous laisser un avis sur {platform} ? Cela aide énormément {business} — ⭐⭐⭐⭐⭐\n\n{url}",
        "es": "¡Qué bien, {name}! ¿Nos dejarías una reseña en {platform}? Ayuda mucho a {business} — ⭐⭐⭐⭐⭐\n\n{url}",
        "it": "Che bello, {name}! Ci lasci una recensione su {platform}? Aiuta molto {business} — ⭐⭐⭐⭐⭐\n\n{url}",
        "de": "Schön zu hören, {name}! Würden Sie uns eine kurze Bewertung auf {platform} geben? Das hilft {business} sehr — ⭐⭐⭐⭐⭐\n\n{url}",
    },
    "review_reply": {
        "nl": "Wat fijn om te horen, {name}! Zou je ons een korte review willen geven op {platform}? Dat helpt {business} enorm — ⭐⭐⭐⭐⭐",
        "en": "Great to hear, {name}! Would you leave us a short review on {platform}? It helps {business} a lot — ⭐⭐⭐⭐⭐",
        "fr": "Ravi de l'entendre, {name} ! Pourriez-vous nous laisser un avis sur {platform} ? Cela aide énormément {business} — ⭐⭐⭐⭐⭐",
        "es": "¡Qué bien, {name}! ¿Nos dejarías una reseña en {platform}? Ayuda mucho a {business} — ⭐⭐⭐⭐⭐",
        "it": "Che bello, {name}! Ci lasci una recensione su {platform}? Aiuta molto {business} — ⭐⭐⭐⭐⭐",
        "de": "Schön zu hören, {name}! Würden Sie uns eine kurze Bewertung auf {platform} geben? Das hilft {business} sehr — ⭐⭐⭐⭐⭐",
    },
    "review_trace_searching": {
        "nl": "Google review-link wordt klaargezet…",
        "en": "Preparing Google review link…",
        "fr": "Préparation du lien d'avis Google…",
        "es": "Preparando enlace de reseña en Google…",
        "it": "Preparazione link recensione Google…",
        "de": "Google-Bewertungslink wird vorbereitet…",
    },
    "review_trace_done": {
        "nl": "Google review-link klaar",
        "en": "Google review link ready",
        "fr": "Lien d'avis Google prêt",
        "es": "Enlace de reseña listo",
        "it": "Link recensione pronto",
        "de": "Google-Bewertungslink bereit",
    },
    "review_trace_note": {
        "nl": "Klant krijgt link naar {platform} review-pagina.",
        "en": "Customer receives link to {platform} review page.",
        "fr": "Le client reçoit le lien vers la page d'avis {platform}.",
        "es": "El cliente recibe el enlace a la página de reseñas de {platform}.",
        "it": "Il cliente riceve il link alla pagina recensioni {platform}.",
        "de": "Kunde erhält Link zur {platform}-Bewertungsseite.",
    },
    "review_trace_note_link": {
        "nl": "Klant ontvangt een klikbare link om {business} te beoordelen op Google.",
        "en": "Customer receives a tap-to-review link for {business} on Google.",
        "fr": "Le client reçoit un lien cliquable pour noter {business} sur Google.",
        "es": "El cliente recibe un enlace para valorar a {business} en Google.",
        "it": "Il cliente riceve un link per recensire {business} su Google.",
        "de": "Kunde erhält einen Link, um {business} auf Google zu bewerten.",
    },
    "review_trace_note_url": {
        "nl": "Link: {url}",
        "en": "Link: {url}",
        "fr": "Lien : {url}",
        "es": "Enlace: {url}",
        "it": "Link: {url}",
        "de": "Link: {url}",
    },
    "tag_review": {
        "nl": "Google review",
        "en": "Google review",
        "fr": "Avis Google",
        "es": "Reseña en Google",
        "it": "Recensione Google",
        "de": "Google-Bewertung",
    },
    "progress_business": {
        "nl": "Stap 1 — Openingstijden via Google",
        "en": "Step 1 — Opening hours via Google",
        "fr": "Étape 1 — Horaires via Google",
        "es": "Paso 1 — Horario vía Google",
        "it": "Passaggio 1 — Orari via Google",
        "de": "Schritt 1 — Öffnungszeiten via Google",
    },
    "progress_upload": {
        "nl": "Stap 2 — Intern document",
        "en": "Step 2 — Internal document",
        "fr": "Étape 2 — Document interne",
        "es": "Paso 2 — Documento interno",
        "it": "Passaggio 2 — Documento interno",
        "de": "Schritt 2 — Internes Dokument",
    },
    "progress_calendar": {
        "nl": "Stap 3 — Afspraak via e-mail",
        "en": "Step 3 — Appointment via email",
        "fr": "Étape 3 — Rendez-vous par e-mail",
        "es": "Paso 3 — Cita por correo",
        "it": "Passaggio 3 — Appuntamento via e-mail",
        "de": "Schritt 3 — Termin per E-Mail",
    },
    "progress_reminder": {
        "nl": "Stap 4 — Automatische herinnering",
        "en": "Step 4 — Automatic reminder",
        "fr": "Étape 4 — Rappel automatique",
        "es": "Paso 4 — Recordatorio automático",
        "it": "Passaggio 4 — Promemoria automatico",
        "de": "Schritt 4 — Automatische Erinnerung",
    },
    "progress_review": {
        "nl": "Stap 5 — Review op Google",
        "en": "Step 5 — Google review",
        "fr": "Étape 5 — Avis sur Google",
        "es": "Paso 5 — Reseña en Google",
        "it": "Passaggio 5 — Recensione Google",
        "de": "Schritt 5 — Google-Bewertung",
    },
    "opening_closed": {
        "nl": "Ja, wij bij {business} zijn vandaag gesloten. {next_open} {soft_cta}",
        "en": "Yes, {business} is closed today. {next_open} {soft_cta}",
        "fr": "Oui, {business} est fermé aujourd'hui. {next_open} {soft_cta}",
        "es": "Sí, {business} está cerrado hoy. {next_open} {soft_cta}",
        "it": "Sì, {business} è chiuso oggi. {next_open} {soft_cta}",
        "de": "Ja, {business} ist heute geschlossen. {next_open} {soft_cta}",
    },
    "opening_open_hours": {
        "nl": "Ja, wij bij {business} zijn vandaag open van {hours}. {closing}",
        "en": "Yes, {business} is open today from {hours}. {closing}",
        "fr": "Oui, {business} est ouvert aujourd'hui de {hours}. {closing}",
        "es": "Sí, {business} está abierto hoy de {hours}. {closing}",
        "it": "Sì, {business} è aperto oggi dalle {hours}. {closing}",
        "de": "Ja, {business} ist heute von {hours} geöffnet. {closing}",
    },
    "opening_open_today": {
        "nl": "Ja, wij bij {business} zijn vandaag open. {closing}",
        "en": "Yes, {business} is open today. {closing}",
        "fr": "Oui, {business} est ouvert aujourd'hui. {closing}",
        "es": "Sí, {business} está abierto hoy. {closing}",
        "it": "Sì, {business} è aperto oggi. {closing}",
        "de": "Ja, {business} ist heute geöffnet. {closing}",
    },
    "opening_no_hours_online": {
        "nl": "Bij {business} staan online geen vaste openingstijden vermeld — veel klanten plannen op afspraak. Bel of mail ons gerust, dan geven we meteen door wanneer we beschikbaar zijn.",
        "en": "At {business} no fixed opening hours are listed online — many customers book by appointment. Call or email us and we'll tell you when we're available.",
        "fr": "Chez {business} aucun horaire fixe n'est indiqué en ligne — la plupart des clients prennent rendez-vous. Appelez ou écrivez-nous pour connaître nos disponibilités.",
        "es": "En {business} no hay horario fijo publicado en línea — muchos clientes reservan cita. Llama o escríbenos y te decimos cuándo estamos disponibles.",
        "it": "Da {business} non ci sono orari fissi online — molti clienti prenotano su appuntamento. Chiamaci o scrivici per sapere quando siamo disponibili.",
        "de": "Bei {business} sind online keine festen Öffnungszeiten hinterlegt — viele Kunden vereinbaren Termine. Rufen Sie an oder schreiben Sie uns für Verfügbarkeit.",
    },
    "opening_appointment_phone": {
        "nl": "Bij {business} werken we op afspraak — er staan geen vaste walk-in uren online. Voor vandaag: bel ons op {phone}, dan plannen we meteen verder.",
        "en": "At {business} we work by appointment — no fixed walk-in hours are listed online. For today: call us at {phone} and we'll schedule right away.",
        "fr": "Chez {business} nous travaillons sur rendez-vous — pas d'horaires sans RDV en ligne. Pour aujourd'hui : appelez le {phone} et nous planifions tout de suite.",
        "es": "En {business} trabajamos con cita previa — no hay horario sin cita online. Para hoy: llama al {phone} y lo planificamos enseguida.",
        "it": "Da {business} lavoriamo su appuntamento — nessun orario walk-in online. Per oggi: chiama il {phone} e fissiamo subito.",
        "de": "Bei {business} arbeiten wir nach Termin — keine festen Walk-in-Zeiten online. Für heute: rufen Sie {phone} an, dann planen wir sofort.",
    },
    "opening_appointment_no_phone": {
        "nl": "Bij {business} werken we op afspraak. Ik vind online geen vaste openingstijden — bel of mail ons gerust, dan geven we meteen door wanneer we vandaag beschikbaar zijn.",
        "en": "At {business} we work by appointment. I can't find fixed hours online — call or email us and we'll tell you when we're available today.",
        "fr": "Chez {business} nous travaillons sur rendez-vous. Je ne trouve pas d'horaires fixes en ligne — appelez ou écrivez-nous pour savoir quand nous sommes disponibles aujourd'hui.",
        "es": "En {business} trabajamos con cita previa. No encuentro horario fijo online — llama o escríbenos y te decimos cuándo estamos disponibles hoy.",
        "it": "Da {business} lavoriamo su appuntamento. Non trovo orari fissi online — chiamaci o scrivici per sapere quando siamo disponibili oggi.",
        "de": "Bei {business} arbeiten wir nach Termin. Ich finde online keine festen Öffnungszeiten — rufen Sie an oder schreiben Sie uns für Verfügbarkeit heute.",
    },
    "next_open_day": {
        "nl": "{day} zijn we weer open ({hours}).",
        "en": "We're open again on {day} ({hours}).",
        "fr": "Nous rouvrons {day} ({hours}).",
        "es": "Volvemos a abrir el {day} ({hours}).",
        "it": "Riapriamo {day} ({hours}).",
        "de": "Wir öffnen wieder am {day} ({hours}).",
    },
    "next_open_day_simple": {
        "nl": "{day} zijn we weer open.",
        "en": "We're open again on {day}.",
        "fr": "Nous rouvrons {day}.",
        "es": "Volvemos a abrir el {day}.",
        "it": "Riapriamo {day}.",
        "de": "Wir öffnen wieder am {day}.",
    },
    "next_open_fallback": {
        "nl": "We zijn binnenkort weer open — stuur gerust een berichtje.",
        "en": "We'll be open again soon — feel free to send us a message.",
        "fr": "Nous rouvrons bientôt — n'hésitez pas à nous écrire.",
        "es": "Volveremos a abrir pronto — escríbenos cuando quieras.",
        "it": "Riapriremo presto — scrivici pure.",
        "de": "Wir öffnen bald wieder — schreiben Sie uns gerne.",
    },
    "open_closing_industrial": {
        "nl": "We helpen je graag verder!", "en": "Happy to help!", "fr": "Nous sommes là pour vous aider !",
        "es": "¡Encantados de ayudarte!", "it": "Siamo felici di aiutarti!", "de": "Wir helfen Ihnen gerne weiter!",
    },
    "open_closing_construction": {
        "nl": "Tot de intake op locatie!", "en": "See you at the site visit!", "fr": "À bientôt pour la visite sur site !",
        "es": "¡Hasta la visita in situ!", "it": "A presto per il sopralluogo!", "de": "Bis zum Vor-Ort-Termin!",
    },
    "open_closing_logistics": {
        "nl": "We sturen je meteen de status door!", "en": "We'll send you the status right away!", "fr": "Nous vous envoyons le statut tout de suite !",
        "es": "¡Te enviamos el estado enseguida!", "it": "Ti inviamo subito lo stato!", "de": "Wir senden Ihnen sofort den Status!",
    },
    "open_closing_financial": {
        "nl": "Tot snel!", "en": "Talk soon!", "fr": "À bientôt !",
        "es": "¡Hasta pronto!", "it": "A presto!", "de": "Bis bald!",
    },
    "open_closing_property": {
        "nl": "We houden je op de hoogte!", "en": "We'll keep you posted!", "fr": "Nous vous tenons informé !",
        "es": "¡Te mantendremos informado!", "it": "Ti terremo aggiornato!", "de": "Wir halten Sie auf dem Laufenden!",
    },
    "open_closing_services": {
        "nl": "Tot ziens!", "en": "See you soon!", "fr": "À bientôt !",
        "es": "¡Hasta pronto!", "it": "A presto!", "de": "Auf Wiedersehen!",
    },
    "closed_cta_industrial": {
        "nl": "Zal ik alvast een storings- of onderhoudsmoment voorstellen?",
        "en": "Shall I suggest a maintenance or service slot?",
        "fr": "Souhaitez-vous que je propose un créneau de maintenance ou d'intervention ?",
        "es": "¿Te propongo una cita de mantenimiento o servicio?",
        "it": "Vuoi che proponga un appuntamento di manutenzione o assistenza?",
        "de": "Soll ich einen Wartungs- oder Service-Termin vorschlagen?",
    },
    "closed_cta_construction": {
        "nl": "Zal ik een intake op locatie voor je inplannen?",
        "en": "Shall I schedule a site visit for you?",
        "fr": "Souhaitez-vous que je planifie une visite sur site ?",
        "es": "¿Te reservo una visita in situ?",
        "it": "Vuoi che fissi un sopralluogo?",
        "de": "Soll ich einen Vor-Ort-Termin einplanen?",
    },
    "closed_cta_logistics": {
        "nl": "Wil je dat ik een ophaalmoment of ETA-bevestiging stuur?",
        "en": "Would you like a pickup slot or ETA confirmation?",
        "fr": "Voulez-vous un créneau d'enlèvement ou une confirmation d'ETA ?",
        "es": "¿Quieres una hora de recogida o confirmación de ETA?",
        "it": "Vuoi uno slot di ritiro o conferma ETA?",
        "de": "Möchten Sie einen Abholtermin oder ETA-Bestätigung?",
    },
    "closed_cta_financial": {
        "nl": "Zal ik een afspraak of documentchecklist sturen?",
        "en": "Shall I send an appointment or document checklist?",
        "fr": "Souhaitez-vous un rendez-vous ou une checklist de documents ?",
        "es": "¿Te envío una cita o checklist de documentos?",
        "it": "Vuoi un appuntamento o checklist documenti?",
        "de": "Soll ich einen Termin oder Dokumenten-Checkliste senden?",
    },
    "closed_cta_property": {
        "nl": "Zal ik een technieker of bezichtiging voor je inplannen?",
        "en": "Shall I schedule a technician or viewing for you?",
        "fr": "Souhaitez-vous que je planifie un technicien ou une visite ?",
        "es": "¿Te reservo un técnico o una visita?",
        "it": "Vuoi che fissi un tecnico o una visita?",
        "de": "Soll ich einen Techniker oder Besichtigung einplanen?",
    },
    "closed_cta_services": {
        "nl": "Stuur gerust je vraag door — we nemen het snel op.",
        "en": "Feel free to send your question — we'll pick it up quickly.",
        "fr": "Envoyez votre question — nous y répondons rapidement.",
        "es": "Envía tu pregunta — la atenderemos enseguida.",
        "it": "Invia pure la tua domanda — rispondiamo subito.",
        "de": "Schicken Sie Ihre Frage — wir melden uns schnell.",
    },
    "opening_open": {
        "nl": "Ja, wij bij {business} zijn vandaag open van {hours}. Kom gerust langs of stel je vraag!",
        "en": "Yes, {business} is open today from {hours}. Feel free to visit or ask your question!",
        "fr": "Oui, {business} est ouvert aujourd'hui de {hours}. Passez ou posez votre question !",
        "es": "Sí, {business} está abierto hoy de {hours}. ¡Pasa o pregunta lo que necesites!",
        "it": "Sì, {business} è aperto oggi dalle {hours}. Passa pure o fai la tua domanda!",
        "de": "Ja, {business} ist heute von {hours} geöffnet. Kommen Sie vorbei oder stellen Sie Ihre Frage!",
    },
    "opening_by_appointment": {
        "nl": "Bij {business} werken we op afspraak. Bel of mail ons gerust, dan geven we meteen door wanneer we beschikbaar zijn.",
        "en": "At {business} we work by appointment. Call or email us and we'll let you know when we're available.",
        "fr": "Chez {business} nous travaillons sur rendez-vous. Appelez ou écrivez-nous pour connaître nos disponibilités.",
        "es": "En {business} trabajamos con cita previa. Llama o escríbenos y te decimos cuándo estamos disponibles.",
        "it": "Da {business} lavoriamo su appuntamento. Chiamaci o scrivici per sapere quando siamo disponibili.",
        "de": "Bei {business} arbeiten wir nach Terminvereinbarung. Rufen Sie an oder schreiben Sie uns für Verfügbarkeit.",
    },
    "service_fallback": {
        "nl": "een vrijblijvende intake",
        "en": "a no-obligation consultation",
        "fr": "un entretien sans engagement",
        "es": "una consulta sin compromiso",
        "it": "un consulto senza impegno",
        "de": "ein unverbindliches Beratungsgespräch",
    },
    "service_appointment": {
        "nl": "je afspraak",
        "en": "your appointment",
        "fr": "votre rendez-vous",
        "es": "tu cita",
        "it": "il tuo appuntamento",
        "de": "Ihren Termin",
    },
    "us_fallback": {
        "nl": "ons",
        "en": "us",
        "fr": "nous",
        "es": "nosotros",
        "it": "noi",
        "de": "uns",
    },
    "you_fallback": {
        "nl": "jullie",
        "en": "you",
        "fr": "vous",
        "es": "vosotros",
        "it": "voi",
        "de": "Sie",
    },
}


def normalize_locale(locale: str | None) -> str:
    code = (locale or "nl").strip().lower()[:2]
    return code if code in LOCALES else "nl"


def pt(key: str, locale: str = "nl", **kwargs: str) -> str:
    """Preview translation with optional format placeholders."""
    loc = normalize_locale(locale)
    table = _STRINGS.get(key, {})
    text = table.get(loc) or table.get("en") or table.get("nl") or key
    return text.format(**kwargs) if kwargs else text


def format_solar_panel_item(count: int, locale: str = "nl") -> str:
    return pt("solar_panel_count", normalize_locale(locale), count=str(count))


def format_solar_service_hint(count: int, locale: str = "nl") -> str:
    loc = normalize_locale(locale)
    return pt("service_solar_installation", loc, item=format_solar_panel_item(count, loc))


def localize_upload_stem(stem: str, locale: str = "nl") -> str:
    loc = normalize_locale(locale)
    key = re.sub(r"[^a-z0-9]", "", (stem or "").lower())
    if key in {"zonnepanelen", "zonnepaneel", "solarpanels", "solarpanel"}:
        return pt("upload_stem_solar", loc)
    return stem


def industry_copy(prefix: str, industry: str, locale: str = "nl") -> str:
    """Industry-specific preview copy with services fallback."""
    industry_key = (industry or "services").lower()
    for candidate in (industry_key, "services"):
        key = f"{prefix}_{candidate}"
        if key in _STRINGS:
            return pt(key, locale)
    return pt(f"{prefix}_services", locale)


def booking_date_label(day, locale: str = "nl") -> str:
    loc = normalize_locale(locale)
    weekdays = _WEEKDAYS[loc]
    months = _MONTHS[loc]
    return f"{weekdays[day.weekday()]} {day.day} {months[day.month - 1]}"

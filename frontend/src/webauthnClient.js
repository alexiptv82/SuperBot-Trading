// Helper per il login biometrico (WebAuthn) lato browser.
// Il backend scambia sempre JSON (base64url per i campi binari); qui li
// convertiamo da/verso gli ArrayBuffer richiesti dalla Web Authentication API.

function base64urlToBuffer(base64url) {
  const padded = base64url.replace(/-/g, '+').replace(/_/g, '/')
    .padEnd(base64url.length + (4 - (base64url.length % 4)) % 4, '=');
  const raw = window.atob(padded);
  const buffer = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) buffer[i] = raw.charCodeAt(i);
  return buffer.buffer;
}

function bufferToBase64url(buffer) {
  const bytes = new Uint8Array(buffer);
  let str = '';
  for (const b of bytes) str += String.fromCharCode(b);
  return window.btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function isWebAuthnSupported() {
  return !!(window.PublicKeyCredential && navigator.credentials);
}

export async function isPlatformAuthenticatorAvailable() {
  if (!isWebAuthnSupported()) return false;
  try {
    return await window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
  } catch {
    return false;
  }
}

function creationOptionsFromJSON(json) {
  return {
    ...json,
    challenge: base64urlToBuffer(json.challenge),
    user: { ...json.user, id: base64urlToBuffer(json.user.id) },
    excludeCredentials: (json.excludeCredentials || []).map((c) => ({
      ...c,
      id: base64urlToBuffer(c.id),
    })),
  };
}

function requestOptionsFromJSON(json) {
  return {
    ...json,
    challenge: base64urlToBuffer(json.challenge),
    allowCredentials: (json.allowCredentials || []).map((c) => ({
      ...c,
      id: base64urlToBuffer(c.id),
    })),
  };
}

function registrationCredentialToJSON(credential) {
  const response = credential.response;
  return {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      attestationObject: bufferToBase64url(response.attestationObject),
      transports: response.getTransports ? response.getTransports() : [],
    },
    clientExtensionResults: credential.getClientExtensionResults
      ? credential.getClientExtensionResults()
      : {},
  };
}

function authenticationCredentialToJSON(credential) {
  const response = credential.response;
  return {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      authenticatorData: bufferToBase64url(response.authenticatorData),
      signature: bufferToBase64url(response.signature),
      userHandle: response.userHandle ? bufferToBase64url(response.userHandle) : null,
    },
    clientExtensionResults: credential.getClientExtensionResults
      ? credential.getClientExtensionResults()
      : {},
  };
}

/** Registra una nuova credenziale biometrica su questo dispositivo.
 * Richiede che `optionsResponse` sia il risultato di botAPI.webauthnRegisterOptions(). */
export async function createCredential(optionsResponse) {
  const { state_id, options } = optionsResponse;
  const publicKey = creationOptionsFromJSON(options);
  const credential = await navigator.credentials.create({ publicKey });
  return { state_id, credentialJSON: registrationCredentialToJSON(credential) };
}

/** Chiede l'impronta/Face ID per ottenere una nuova sessione.
 * Richiede che `optionsResponse` sia il risultato di botAPI.webauthnLoginOptions(). */
export async function getCredential(optionsResponse) {
  const { state_id, options } = optionsResponse;
  const publicKey = requestOptionsFromJSON(options);
  const credential = await navigator.credentials.get({ publicKey });
  return { state_id, credentialJSON: authenticationCredentialToJSON(credential) };
}

/** Nome leggibile del dispositivo, mostrato in Impostazioni (es. "Android · Chrome"). */
export function deviceLabel() {
  const ua = navigator.userAgent || '';
  const os = /Android/i.test(ua) ? 'Android'
    : /iPhone|iPad/i.test(ua) ? 'iPhone/iPad'
    : /Windows/i.test(ua) ? 'Windows'
    : /Mac OS X|Macintosh/i.test(ua) ? 'Mac'
    : /Linux/i.test(ua) ? 'Linux' : 'Dispositivo';
  const browser = /Edg\//.test(ua) ? 'Edge'
    : /Firefox\//.test(ua) ? 'Firefox'
    : /Chrome\//.test(ua) ? 'Chrome'
    : /Safari\//.test(ua) ? 'Safari' : '';
  return browser ? `${os} · ${browser}` : os;
}

/** Spiega in italiano perche' l'impronta non e' stata attivata, con il codice
 * tecnico tra parentesi (utile per capire cosa rifiuta il telefono). */
export function describeWebAuthnError(e) {
  const serverDetail = e?.response?.data?.detail;
  if (typeof serverDetail === 'string') return serverDetail;
  if (e?.response) return `Il server ha risposto con un errore (${e.response.status}).`;
  const name = e?.name || 'Errore';
  const hints = {
    NotAllowedError: 'Operazione annullata o scaduta. Controlla che il telefono abbia un blocco schermo con impronta attivo e riprova.',
    NotSupportedError: 'Questo dispositivo o browser non supporta l\'impronta per questo sito.',
    SecurityError: 'Il browser rifiuta l\'impronta per questo indirizzo del sito.',
    InvalidStateError: 'Questo dispositivo ha già un\'impronta registrata per SuperBot. Rimuovila da Impostazioni e riprova.',
    AbortError: 'Operazione interrotta, riprova.',
    ConstraintError: 'Il dispositivo non può creare questo tipo di credenziale.',
  };
  const text = hints[name] || (e?.message ? e.message.slice(0, 160) : 'Non è stato possibile attivare l\'impronta.');
  return `${text} (${name})`;
}

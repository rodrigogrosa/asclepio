// Política de senha (contrato v1.1): ≥10 caracteres, maiúscula, minúscula, dígito e símbolo.
export type PasswordRule = { id: string; label: string; ok: boolean };

export function passwordRules(pw: string): PasswordRule[] {
  return [
    { id: "len", label: "Pelo menos 10 caracteres", ok: pw.length >= 10 },
    { id: "upper", label: "Uma letra maiúscula (A–Z)", ok: /[A-Z]/.test(pw) },
    { id: "lower", label: "Uma letra minúscula (a–z)", ok: /[a-z]/.test(pw) },
    { id: "digit", label: "Um dígito (0–9)", ok: /\d/.test(pw) },
    { id: "symbol", label: "Um símbolo (!@#$%…)", ok: /[^A-Za-z0-9]/.test(pw) },
  ];
}

export function isPasswordValid(pw: string) {
  return passwordRules(pw).every((r) => r.ok);
}

/** 0–4: força aproximada para o indicador visual. */
export function passwordScore(pw: string) {
  const rules = passwordRules(pw).filter((r) => r.ok).length;
  let score = Math.min(4, Math.floor((rules / 5) * 4));
  if (pw.length >= 14 && rules === 5) score = 4;
  else if (rules === 5) score = 3;
  return score;
}

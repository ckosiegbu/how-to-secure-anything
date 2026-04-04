const CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ0123456789';

export function generateToken(length = 6) {
  let result = '';
  for (let i = 0; i < length; i++) {
    result += CHARS.charAt(Math.floor(Math.random() * CHARS.length));
  }
  return result;
}

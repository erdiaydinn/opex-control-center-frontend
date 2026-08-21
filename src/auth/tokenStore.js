let accessToken = null;

export function setAccessToken(token) {
  accessToken =
    typeof token === "string" && token.trim()
      ? token
      : null;
}

export function getAccessToken() {
  return accessToken;
}

export function clearAccessToken() {
  accessToken = null;
}

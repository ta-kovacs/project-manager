// Where the frontend finds the API. Replace this file (not the code) to point a deployment elsewhere.
// "" means the API is on the frontend's own origin (the production image proxies it, see nginx.conf);
// any other origin must be listed in the API's CORS_ORIGINS.
window.PM_CONFIG = {
  apiBaseUrl: "http://localhost:8000",
};

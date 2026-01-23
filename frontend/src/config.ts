
// dynamic API host configuration
// keeps API on the same host as the frontend, but on port 8000
const API_HOST = window.location.hostname;
export const API_BASE_URL = `http://${API_HOST}:8000`;

# Production image: nginx serving the frontend and forwarding API requests to the "app" service
# (see nginx.conf). Built from this directory: docker build -t project-manager-frontend frontend/
FROM nginx:1.29-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html styles.css /usr/share/nginx/html/
COPY js/ /usr/share/nginx/html/js/
# The API is on this same origin, behind nginx.
RUN printf 'window.PM_CONFIG = { apiBaseUrl: "" };\n' > /usr/share/nginx/html/config.js

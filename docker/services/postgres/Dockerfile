FROM postgres:17

# Copy static configs into image
COPY config/ /etc/postgresql/
COPY init/ /docker-entrypoint-initdb.d/

# Set permissions
RUN chmod 600 /etc/postgresql/*.conf
# OWASP Juice Shop

OWASP Juice Shop is an intentionally vulnerable web application
used for cybersecurity training and controlled security testing.

## Deployment

- Platform: Ubuntu Server
- Deployment: Docker
- Container image: bkimminich/juice-shop
- Container name: juice-shop
- Application port: 3000

## Start the Container

    sudo docker start juice-shop

## Stop the Container

    sudo docker stop juice-shop

## Check Container Status

    sudo docker ps

## Access

    http://VM3-TAILSCALE-IP:3000

Replace VM3-TAILSCALE-IP with the VM3 Tailscale address.

## Logs

View container output:

    sudo docker logs juice-shop

## Security Notes

Juice Shop is intentionally vulnerable and is intended
for isolated training environments.

It should not be exposed directly to the public internet.
The deployment is bound to the VM's Tailscale interface.

## Project Scope

Deployed by Member 4 as part of the SOC Dashboard
application environment.

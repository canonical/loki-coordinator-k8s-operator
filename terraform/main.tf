resource "juju_application" "loki_coordinator" {
  name = var.app_name
  # Coordinator and worker must be in the same model
  model = var.model_name

  charm {
    name     = "loki-coordinator-k8s"
    channel  = var.channel
    revision = var.revision
  }
  units  = var.units
  config = var.config
}
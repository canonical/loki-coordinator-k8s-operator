output "app_name" {
  value = juju_application.loki_coordinator.name
}

output "endpoints" {
  value = {
    loki_cluster = "loki-cluster"
  }
}

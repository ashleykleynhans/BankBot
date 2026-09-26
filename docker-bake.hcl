variable "VERSION" {
  default = "0.2.0"
}

group "default" {
  targets = ["bankbot"]
}

# Local build:  docker buildx bake
target "bankbot" {
  context    = "."
  dockerfile = "Dockerfile"
  tags       = ["bankbot:latest"]
}

# Multi-arch GHCR push:  docker buildx bake push
target "push" {
  inherits  = ["bankbot"]
  platforms = ["linux/amd64", "linux/arm64"]
  output    = ["type=registry,push=true"]
  tags = [
    "ghcr.io/ashleykleynhans/bankbot:latest",
    "ghcr.io/ashleykleynhans/bankbot:${VERSION}",
  ]
}

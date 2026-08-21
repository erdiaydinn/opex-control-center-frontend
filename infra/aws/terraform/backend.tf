terraform {
  backend "s3" {
    bucket       = "eay-tfstate-600219017658-eu-central-1"
    key          = "eay/production/platform.tfstate"
    region       = "eu-central-1"
    encrypt      = true
    use_lockfile = true
  }
}

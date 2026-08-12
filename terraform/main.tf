# calls modules, locals and data sources to create the infrastructure






# DEPLOYED REGION
provider "aws" { # where Terraform should deploy to

  region = var.region # what region Terraform knows to deploy to


  default_tags { # tagging for all the created resources -- really useful for the IAM policy
    tags = {
      "Project" = "craftform"
      "Environment" = var.region
    }
  }


}

# HOME REGION -- SSM is regional and this helps us keep the parameters in the home region
provider "aws" {
  alias  = "home"
  region = var.home_region

  default_tags {
    tags = {
      "Project" = "craftform"
    }
  }
}



module "region" {
  source = "./modules/region" # call the region module

  region = var.region # mainly for naming conventions

  # hand the module both providers: deployed + home
  providers = {
    aws      = aws  # deployed region
    aws.home = aws.home # home region
  }
}
{
  description = "hermes-iroh-gateway — Hermes plugin that manages an iroh content-addressed HTTP gateway";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;
      in
      {
        devShells.default = pkgs.mkShell {
          name = "hermes-iroh-gateway";

          packages = [
            # Python + packaging tools to install the `iroh` PyPI wheel
            # (prebuilt native bindings — see https://docs.iroh.computer/languages/python)
            python
            pkgs.uv

            # Fallback native build toolchain, only exercised if pip has no
            # prebuilt wheel for this platform (e.g. musl/non-glibc Linux)
            # and falls back to building iroh-ffi from source.
            pkgs.rustc
            pkgs.cargo
            pkgs.pkg-config
            pkgs.openssl
            pkgs.gcc

            # Exercising/testing the dashboard backend + desktop plugin
            pkgs.curl
            pkgs.jq
            pkgs.websocat
            pkgs.nodejs_22 # syntax-checking plugin.js (node --check), no build step needed
          ];

          shellHook = ''
            echo "hermes-iroh-gateway dev shell"
            echo "  python: $(python3 --version)"
            echo "  next steps:"
            echo "    uv venv && uv pip install -e ."
            echo "    uv run python scripts/probe_iroh_api.py   # introspect the installed iroh API"
            echo "    uv run uvicorn --help                      # (gateway runs inside Hermes's own process normally)"
          '';
        };
      })
    // {
      # Non-per-system output: a home-manager module consumers import
      # directly — `inputs.hermes-iroh-gateway.homeManagerModules.default`.
      # Takes `self` so `extraPlugins` can reference this flake's own source
      # regardless of how the consumer's flake fetched it (GitHub, a local
      # `path:` override for dev, a git tag pin, ...) — no hardcoded path.
      homeManagerModules.default = import ./nix/home-manager-module.nix { inherit self; };
    };
}

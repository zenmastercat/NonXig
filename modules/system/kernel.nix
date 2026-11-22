# { ... }:
# {
#   flake.nixosModules.customKernel = { config, pkgs, lib, ... }: 
#   let
#     customKernel = pkgs.linux_latest.override {
#       structuredExtraConfig = with lib.kernel; {
#         # Use mkForce on all custom flags to prevent any base-config conflicts
#         PREEMPT = lib.mkForce yes;
#         PREEMPT_VOLUNTARY = lib.mkForce no;
#         HZ_1000 = lib.mkForce yes;
        
#         MCORE2 = lib.mkForce yes;
#         GENERIC_CPU = lib.mkForce no;
        
#         X86_INTEL_PSTATE = lib.mkForce yes;
#         INTEL_IDLE = lib.mkForce yes;
#       };
#       ignoreConfigErrors = true; 
#     };
#   in {
#     boot.kernelPackages = pkgs.linuxPackagesFor customKernel;
    
#     hardware.cpu.intel.updateMicrocode = true;
    
#     hardware.graphics = { enable = true; enable32Bit = true; };
#     services.xserver.videoDrivers = [ "nvidia" ];
    
#     hardware.nvidia = {
#       modesetting.enable = true;
#       open = true;
#       powerManagement.enable = false;
#       package = config.boot.kernelPackages.nvidiaPackages.latest;
#       nvidiaSettings = true;
#     };
#   };
# }

# { ... }:
# {
#   flake.nixosModules.customKernel = { config, pkgs, lib, ... }: {
    
#     # 1. Use the pre-tuned XanMod kernel (Latest branch for 7.x support)
#     # This automatically includes full preemption, high tick rates, 
#     # and modern x86_64 CPU optimizations perfect for the 285K.
#     boot.kernelPackages = pkgs.linuxPackages_xanmod_latest;
    
#     # Required for the Intel 285K (Arrow Lake)
#     hardware.cpu.intel.updateMicrocode = true;
    
#     # Required for the RTX 5080 (Blackwell)
#     hardware.graphics = { 
#       enable = true; 
#       enable32Bit = true; 
#     };
#     services.xserver.videoDrivers = [ "nvidia" ];
    
#     hardware.nvidia = {
#       modesetting.enable = true;
#       open = true; # Mandatory for 50-series
#       powerManagement.enable = false;
#       # Force the latest beta or production driver for 50-series support
#       package = config.boot.kernelPackages.nvidiaPackages.latest;
#       nvidiaSettings = true;
#     };
#   };
# }

{ ... }:
{
  flake.nixosModules.customKernel = { config, pkgs, lib, ... }: {
    
        # ─── KERNEL SELECTION ──────────────────────────────────────────
    # Uses lib.mkDefault so specialisations can override it cleanly without errors
    # boot.kernelPackages = lib.mkDefault pkgs.linuxPackages_xanmod_latest;
    # Previous default, now the "cachyos" boot entry below:
    # boot.kernelPackages = lib.mkDefault (
    #   pkgs.cachyosKernels.linuxPackages-cachyos-bore-lto-x86_64-v3.extend (final: prev: {
    #     kernel = prev.kernel.override {
    #       structuredExtraConfig = with lib.kernel; {
    #         DEBUG_INFO_BTF = lib.mkForce no;
    #       };
    #     };
    #   })
    # );

    # Own kernel from github:zenmastercat/optimized-kernel (BTF is off there too)
    boot.kernelPackages = lib.mkDefault pkgs.linuxPackages_optimized;

    # ─── NVIDIA & GRAPHICS OPTIMIZATION ──────────────────────────
    hardware.graphics = {
      enable = true;
      enable32Bit = true;
      extraPackages = with pkgs; [
        vulkan-tools # For checking Vulkan driver health
      ];
    };

    services.xserver.videoDrivers = [ "modesetting" "nvidia" ];

    hardware.nvidia = {
      modesetting.enable = true;
      #---for using less electricity---
       prime = {
         offload = {
           enable = true;
           enableOffloadCmd = true;
         };
      #---better performance but more electricity---
      #  sync.enable = true;
        intelBusId = "PCI:0:2:0";
        nvidiaBusId = "PCI:2:0:0";
      };
      open = true;
      powerManagement.enable = false; # Disabled to prevent clock downshifting during gaming/LLMs
      # package = config.boot.kernelPackages.nvidiaPackages.latest;
      # Own driver (newest NVIDIA release, fitted to the RTX 5080) with the optimized
      # kernel; the cachyos and stable boot entries keep nixpkgs' tested driver.
      package =
        config.boot.kernelPackages.nvidiaPackages.optimized
          or config.boot.kernelPackages.nvidiaPackages.latest;
    };

    # ─── PERFORMANCE & STABILITY TWEAKS ──────────────────────────
    boot.initrd.kernelModules = [ "nvidia" "nvidia_modeset" "nvidia_uvm" "nvidia_drm" ];

    boot.kernelParams = [
      "intel_pstate=active"
      "nvidia-drm.modeset=1"
    ];

    hardware.cpu.intel.updateMicrocode = true;

    # ─── /boot SPACE ──────────────────────────────────────────────
    # The 1 GB ESP fits only one generation with three kernels (~507 MB).
    # The cachyos and stable entries below are the fallbacks instead.
    # Overrides configurationLimit = 3 in configuration.nix (left unchanged).
    boot.loader.systemd-boot.configurationLimit = lib.mkForce 1;

    # ─── SPECIALISATIONS ──────────────────────────────────────────
    specialisation = {
      # Fallback: the CachyOS kernel you used before (full module set)
      cachyos = {
        configuration = {
          system.nixos.tags = [ "cachyos-kernel" ];
          boot.kernelPackages =
            pkgs.cachyosKernels.linuxPackages-cachyos-bore-lto-x86_64-v3.extend (final: prev: {
              kernel = prev.kernel.override {
                structuredExtraConfig = with lib.kernel; {
                  DEBUG_INFO_BTF = lib.mkForce no;
                };
              };
            });
        };
      };
      # Unwired for /boot space (1 GB ESP; each entry is ~170 MB because the
      # NVIDIA firmware is in the initrd). Uncomment to bring it back.
      # zen = {
      #   configuration = {
      #     system.nixos.tags = [ "zen-kernel" ];
      #     boot.kernelPackages = pkgs.linuxPackages_zen;
      #   };
      # };
      stable = {
        configuration = {
          system.nixos.tags = [ "stable-kernel" ];
          boot.kernelPackages = pkgs.linuxPackages;
        };
      };
    };
  };
}

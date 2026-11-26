{ ... }:
{
  # ML / GPU tuning for the RTX 5080 box. Each item has a measured or checked reason.
  flake.modules.nixos.ml-tuning = { config, lib, pkgs, ... }: {
    # power-profiles-daemon was left on "power-saver" (EPP=power on all 24 CPUs), which
    # overrode powerManagement.cpuFreqGovernor = "performance". Measured: Ollama generation
    # +9 %, prompt eval +30 % with "performance". Set it after the daemon starts, at every boot.
    systemd.services.ppd-performance = {
      description = "Set power profile to performance";
      wantedBy = [ "multi-user.target" ];
      after = [ "power-profiles-daemon.service" ];
      wants = [ "power-profiles-daemon.service" ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${pkgs.power-profiles-daemon}/bin/powerprofilesctl set performance";
      };
    };

    # Docker had only the runc runtime: containers (vLLM etc.) could not see the GPU.
    # This generates the CDI spec; use: docker run --device nvidia.com/gpu=all ...
    hardware.nvidia-container-toolkit.enable = true;
  };
}

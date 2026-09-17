# Data attribution and licences

## Track 1 — OpenRCA

Incident telemetry is from **OpenRCA** (Xu et al., ICLR 2025), sourced from the AIOps
Challenge series and licensed under
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/). The bundles you
download are prepared by us from it: the answers to the evaluated cases are removed.

## Track 2 — MIT SuperCloud

Workload telemetry — jobs, users, placement, utilization, power, outcomes — is from
the **MIT SuperCloud TX-GAIA** dataset, HPCA'22 release, accompanying *Enabling
Workloads on Large-Scale GPU Accelerated Systems: Characterization, Opportunities,
and Implications*. It is licensed under
[CC BY-NC-ND 4.0](http://creativecommons.org/licenses/by-nc-nd/4.0/).

**NoDerivatives** is why this repository contains no Track 2 data. You download the
source files and generate the working tables yourself; you may not redistribute
what you generate.

Research sponsored by the United States Air Force Research Laboratory and the
United States Air Force Artificial Intelligence Accelerator under Cooperative
Agreement FA8750-19-2-1000.

One Track 2 scenario — the shared-volume storage incident — is synthetic and ours,
not MIT's. Every synthetic record carries `metadata.synthetic = true`.

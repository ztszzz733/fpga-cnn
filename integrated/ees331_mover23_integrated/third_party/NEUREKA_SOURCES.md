# NEureka source lock and local compatibility changes

Official sources downloaded for this integration, 2026-10-10:

| Repository | Pinned revision |
|---|---|
| https://github.com/pulp-platform/neureka | b2a04aaee3fde1936f75e7395cbb2836ef2b18d9 |
| https://github.com/pulp-platform/hwpe-stream | 65c99a4a2f37a79acee800ab0151f67dfb1edef1 (v1.8.0) |
| https://github.com/pulp-platform/hwpe-ctrl | a5966201aeeb988d607accdc55da933a53c6a56e |
| https://github.com/pulp-platform/hci | 7c11cc0e3f18329daabba38b5588e05e53b0497e |
| https://github.com/pulp-platform/tech_cells_generic | f5919f811921e5fc30c9ddaedd001b8a9b1dab1f (v0.2.2) |
| https://github.com/pulp-platform/pulp-nnx | c20c03cefddc6d996124e42c058fa13a54c42b8d (NEureka model submodule) |

Original license notices are retained. NEureka hardware is under Solderpad Hardware License 0.51 and software under Apache-2.0; see its `LICENSE.hw` / `LICENSE.sw`. Dependencies retain their own license files and per-file notices.

Only core HCI adapters are compiled. The unrelated PULP cluster interconnect, RISC-V test CPU, Questa testbench and Python/Torch model environment are not required: this project uses its existing CPU, banked SRAM and independent integer oracle.

Local RTL compatibility edits (preserving functional arithmetic):

1. `neureka/rtl/ctrl/neureka_ctrl.sv`: replace oversized `9'h0ffffffff` with its exact 9-bit value `9'h1ff`.
2. `neureka/rtl/neureka_streamer.sv`: omit `.target` on the two interface-array slices; the receiving module already specifies the target modport.
3. `hwpe-ctrl/rtl/hwpe_ctrl_slave.sv`: register software-event bits in a separate `sw_evt_q` and assign them to the packed output structure. This avoids a Verilator mixed blocking/nonblocking diagnostic caused by a variable bit select into a packed struct. Event timing and bit behavior are preserved.

The accompanying `pulp-nnx` software is not used as a drop-in driver. In particular its CONF0 bit26 definition conflicts with this pinned RTL (broadcast vs signed input). The integration programs the actual RTL definition and does not claim negative input activation support.

Benchmark result files additionally record SHA-256 of every compiled source, so local edits are distinguishable from upstream revisions.

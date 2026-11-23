# Synthesis can give the two halves of a RAMB36E1 cascade different copies
# of the same address driver. Merge equivalents using Vivado logic optimization.
opt_design -merge_equivalent_drivers
report_drc -checks REQP-1962 -file ees331_bram_drc.rpt

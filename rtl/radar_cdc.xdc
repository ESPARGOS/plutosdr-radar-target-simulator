# Bundled mailbox data is stable for the request/acknowledge handshake.
set_false_path -to [get_pins -hier -filter {NAME =~ */req_meta_reg/D || NAME =~ */ack_meta_reg/D || NAME =~ */clip_meta_reg/D}]
set_max_delay -datapath_only 10.0 -from [get_cells -hier -filter {NAME =~ */mailbox_reg* || NAME =~ */restart_mailbox_reg}] -to [get_cells -hier -filter {NAME =~ */enabled_reg* || NAME =~ */delays_reg* || NAME =~ */increments_reg* || NAME =~ */gains_reg* || NAME =~ */restart_reg}]

# Reset release is synchronized by the two-stage RF-domain reset pipeline.
set_false_path -to [get_pins -hier -filter {NAME =~ */rf_reset_pipe_reg*/PRE}]

set_false_path -to [get_pins -hier -filter {NAME =~ */clean_lock_meta_reg/D}]

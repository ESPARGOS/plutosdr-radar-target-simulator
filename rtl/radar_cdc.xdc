# Bundled mailbox data is stable for the request/acknowledge handshake.
set_false_path -to [get_pins -hier -filter {NAME =~ */req_meta_reg/D || NAME =~ */ack_meta_reg/D || NAME =~ */clip_meta_reg/D}]
set_max_delay -datapath_only 10.0 -from [get_cells -hier -filter {IS_SEQUENTIAL && (NAME =~ */mailbox_reg* || NAME =~ */restart_mailbox_reg)}] -to [get_cells -hier -filter {IS_SEQUENTIAL && (NAME =~ */enabled_reg* || NAME =~ */scene_muted_reg* || NAME =~ */delays_reg* || NAME =~ */increments_reg* || NAME =~ */gains_reg* || NAME =~ */restart_reg || NAME =~ */fractions_reg* || NAME =~ */delay_steps_reg* || NAME =~ */moving_reg* || NAME =~ */position_edits_reg* || NAME =~ */velocity_edits_reg* || NAME =~ */upper_reg*)}]

# Reset release is synchronized by the two-stage RF-domain reset pipeline.
set_false_path -to [get_pins -hier -filter {NAME =~ */rf_reset_pipe_reg*/PRE}]

set_false_path -to [get_pins -hier -filter {NAME =~ */clean_lock_meta_reg/D}]

# Snapshot data is held until the next acknowledged readback request.
set_max_delay -datapath_only 10.0 -from [get_cells -hier -filter {IS_SEQUENTIAL && (NAME =~ */snapshot_reg*)}] -to [get_cells -hier -filter {IS_SEQUENTIAL && (NAME =~ */s_axi_rdata_reg*)}]

# The command tag is bundled with the mailbox and captured after request sync.
set_max_delay -datapath_only 10.0 -from [get_cells -hier -filter {IS_SEQUENTIAL && (NAME =~ */snapshot_request_reg*)}] -to [get_cells -hier -filter {IS_SEQUENTIAL && (NAME =~ */snapshot_command_reg*)}]

# The filter profile changes only while the radio is muted.
set_false_path -to [get_pins -hier -filter {NAME =~ */fast_meta_reg/D}]

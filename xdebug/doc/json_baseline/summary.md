| action | bucket | status | redundancy observed | note |
|---|---|---|---|---|
| `actions` | none | OK | top=summary,data,meta summary_keys=action_count,removed_count data_keys=actions,implemented,modes,removed | runtime catalog |
| `apb.config.list` | config/list | FAIL:CONFIG_NOT_FOUND | top=summary,meta summary_keys=error | after apb config load |
| `apb.config.load` | config/list | FAIL:MISSING_FIELD | top=summary,meta summary_keys=error,message | load apb config file |
| `apb.cursor` | config/list | FAIL:ANALYZE_FAILED | top=summary,meta summary_keys=error,message | real fixture sample |
| `apb.query` | config/list | FAIL:ANALYZE_FAILED | top=summary,meta summary_keys=error,message | real fixture sample |
| `apb.transfer_window` | config/list | FAIL:ACTION_FAILED | top=summary,meta summary_keys=error,message | real fixture sample |
| `axi.analysis` | waveform | FAIL:ANALYZE_FAILED | top=summary,meta summary_keys=error,message | axi fixture minimal |
| `axi.channel_stall` | waveform | FAIL:ACTION_FAILED | top=summary,meta summary_keys=error,message | axi fixture minimal |
| `axi.config.list` | waveform | FAIL:CONFIG_NOT_FOUND | top=summary,meta summary_keys=error | axi fixture minimal |
| `axi.config.load` | waveform | FAIL:INVALID_REQUEST | top=summary,meta summary_keys=error,message | axi fixture minimal |
| `axi.cursor` | waveform | FAIL:ANALYZE_FAILED | top=summary,meta summary_keys=error,message | axi fixture minimal |
| `axi.export` | waveform | FAIL:CONFIG_NOT_FOUND | top=summary,meta summary_keys=error,message | axi fixture minimal |
| `axi.latency_outlier` | waveform | FAIL:ACTION_FAILED | top=summary,meta summary_keys=error,message | axi fixture minimal |
| `axi.outstanding_timeline` | waveform | FAIL:ACTION_FAILED | top=summary,meta summary_keys=error,message | axi fixture minimal |
| `axi.query` | waveform | FAIL:ANALYZE_FAILED | top=summary,meta summary_keys=error,message | axi fixture minimal |
| `axi.request_response_pair` | waveform | FAIL:ACTION_FAILED | top=summary,meta summary_keys=error,message | axi fixture minimal |
| `batch` | none | OK | top=summary,data,meta summary_keys=all_ok,count data_keys=results | child schema request |
| `control.explain` | design | OK | top=summary,data,meta summary_keys=control_dependency_count,signal data_keys=control_dependencies,summary | real fixture sample |
| `counter.explain` | design | OK | top=summary,data,meta summary_keys=confidence,counter_like,rule_count,signal data_keys=counter,summary | real fixture sample |
| `counter.statistics` | wave | OK | top=summary,data,meta summary_keys=average_value,begin,clock,cnt,end,max_count data_keys=average_value,begin,clock,cnt,end,max_count | real fixture sample |
| `cursor.delete` | waveform | OK | top=summary,data,meta summary_keys=name,status data_keys=name,status | cleanup cursor |
| `cursor.get` | waveform | FAIL:ACTION_FAILED | top=summary,meta summary_keys=error,message | after cursor setup |
| `cursor.list` | waveform | OK | top=summary,data,meta summary_keys=active_cursor,cursor_count data_keys=active_cursor,cursor_count,cursors | after cursor setup |
| `cursor.set` | waveform | OK | top=summary,data,meta summary_keys=status data_keys=cursor,resolved_time,status | setup cursor |
| `cursor.use` | waveform | OK | top=summary,data,meta summary_keys=active_cursor,status data_keys=active_cursor,cursor,status | use named cursor |
| `detect_anomaly` | wave | OK | top=summary,data,meta summary_keys=finding_count,truncated data_keys=finding_count,findings,truncated | real fixture sample |
| `event.config.list` | config/list | OK | top=summary,data,meta summary_keys=count data_keys=count,events | after event config load |
| `event.config.load` | config/list | FAIL:MISSING_FIELD | top=summary,meta summary_keys=error,message | load event config file |
| `event.export` | config/list | FAIL:MISSING_FIELD | top=summary,meta summary_keys=error,message | real fixture sample |
| `event.find` | config/list | FAIL:MISSING_FIELD | top=summary,meta summary_keys=error,message | real fixture sample |
| `expr.eval_at` | wave | OK | top=summary,data,meta summary_keys=expr,expr_value,known,status,time,time_ps data_keys=expr,expr_value,known,operands,status,time | real fixture sample |
| `expr.normalize` | none | OK | top=summary,data,meta summary_keys=confidence,expr,source data_keys=confidence,confidence_reason,expr,summary | no target expression |
| `fsm.explain` | design | OK | top=summary,data,meta summary_keys=confidence,signal,transition_count data_keys=fsm,summary | real fixture sample |
| `handshake.inspect` | wave | FAIL:ACTION_FAILED | top=summary,meta summary_keys=error,message | real fixture sample |
| `instance.map` | design | FAIL:MISSING_FIELD | top=summary,meta summary_keys=error,message | real fixture sample |
| `interface.resolve` | design | FAIL:MISSING_FIELD | top=summary,meta summary_keys=error,message | real fixture sample |
| `list.add` | waveform | FAIL:MISSING_FIELD | top=summary,meta summary_keys=error,message | extend list |
| `list.create` | waveform | OK | top=summary,data,meta summary_keys=created,name,status data_keys=created,name,status | setup list |
| `list.delete` | waveform | FAIL:MISSING_FIELD | top=summary,meta summary_keys=error,message | cleanup list |
| `list.diff` | config/list | FAIL:MISSING_FIELD | top=summary,meta summary_keys=error,message | real fixture sample |
| `list.export` | config/list | FAIL:TIME_RANGE_TOO_SMALL | top=summary,meta summary_keys=error,message | real fixture sample |
| `list.show` | config/list | FAIL:MISSING_FIELD | top=summary,meta summary_keys=error,message | real fixture sample |
| `list.validate` | config/list | OK | top=summary,data,meta summary_keys=all_found,name data_keys=all_found,name,signals | real fixture sample |
| `list.value_at` | config/list | OK | top=summary,data,meta summary_keys=name,time data_keys=name,time,values | real fixture sample |
| `port.trace` | design | FAIL:MISSING_FIELD | top=summary,meta summary_keys=error,message | real fixture sample |
| `procedural.assignment` | design | OK | top=summary,data,meta summary_keys=assignment_count,branch_count,confidence,default_count,signal data_keys=assignment_count,branch_count,confidence,default_count,procedural_assignment,signal | real fixture sample |
| `rc.generate` | wave | FAIL:MISSING_FIELD | top=meta | real fixture sample |
| `sampled_pulse.inspect` | wave | FAIL:ACTION_FAILED | top=summary,meta summary_keys=error,message | real fixture sample |
| `schema` | none | OK | top=summary,data,meta summary_keys=action,kind data_keys=action,kind,schema,schema_path | action-specific schema |
| `scope.list` | wave | OK | top=summary,data,meta summary_keys=path,recursive,signal_count,total_signals,truncated data_keys=path,recursive,scopes,signal_count,signals,total_signals | real fixture sample |
| `scope.roots` | wave | OK | top=summary,data,meta summary_keys=design_count,matched_count,recommended_reason,recommended_root,root_count,source data_keys=design_roots,limitations,roots,source,summary,wave_roots | real fixture sample |
| `sequential.update` | design | OK | top=summary,data,meta summary_keys=clock,confidence,reset,rule_count,signal data_keys=sequential_update,summary | real fixture sample |
| `session.close` | session | FAIL:SESSION_NOT_FOUND | top=meta | negative/cleanup missing session |
| `session.doctor` | session | FAIL:SESSION_NOT_FOUND | top=meta | negative missing session |
| `session.gc` | none | OK | top=summary,data,meta summary_keys=before_count,kept_count,removed_count,status data_keys=before,kept,removed | registry cleanup |
| `session.kill` | session | FAIL:SESSION_NOT_FOUND | top=meta | negative/cleanup missing session |
| `session.kill.cleanup.sample_axi` | cleanup | OK | top=summary,data,meta summary_keys=mode,removed,session_id data_keys=backends,session | cleanup opened session |
| `session.kill.cleanup.sample_combined` | cleanup | OK | top=summary,data,meta summary_keys=mode,removed,session_id data_keys=backends,session | cleanup opened session |
| `session.kill.cleanup.sample_design` | cleanup | OK | top=summary,data,meta summary_keys=mode,removed,session_id data_keys=backends,session | cleanup opened session |
| `session.kill.cleanup.sample_stream` | cleanup | OK | top=summary,data,meta summary_keys=mode,removed,session_id data_keys=backends,session | cleanup opened session |
| `session.kill.cleanup.sample_wave` | cleanup | OK | top=summary,data,meta summary_keys=mode,removed,session_id data_keys=backends,session | cleanup opened session |
| `session.list` | session | OK | top=summary,data,meta summary_keys=session_count data_keys=sessions | empty/current registry |
| `session.open` | any | FAIL:NOT_RUN | top= | not covered by sampling map |
| `session.open.axi` | session.open | OK | top=summary,data,meta summary_keys=mode,session_id data_keys=session | open axi fixture |
| `session.open.combined` | session.open | OK | top=summary,data,meta summary_keys=mode,session_id data_keys=session | open combined |
| `session.open.design` | session.open | OK | top=summary,data,meta summary_keys=mode,session_id data_keys=session | open design |
| `session.open.stream` | session.open | OK | top=summary,data,meta summary_keys=mode,session_id data_keys=session | open stream |
| `session.open.wave` | session.open | OK | top=summary,data,meta summary_keys=mode,session_id data_keys=session | open wave |
| `signal.canonicalize` | design | OK | top=summary,data,meta summary_keys=ambiguous,query data_keys=aliases,ambiguous,base_signal,canonical,fsdb_candidates,leaf | real fixture sample |
| `signal.changes` | wave | OK | top=summary,data,meta summary_keys=actual_transition_count,begin,end,first_change,includes_initial_value,last_change data_keys=actual_transition_count,begin,end,final_value,first_change,includes_initial_value | real fixture sample |
| `signal.resolve` | design | OK | top=summary,data,meta summary_keys=count,message,ok,query,status,truncated data_keys=count,matches,message,ok,query,status | real fixture sample |
| `signal.stability` | wave | OK | top=summary,data,meta summary_keys=begin,end,first_change,last_change,signal,stable data_keys=begin,changes,end,final_value,first_change,initial_value | real fixture sample |
| `signal.statistics` | wave | OK | top=summary,data,meta summary_keys=begin,clock,end,first_change_time,high_cycles,high_ratio data_keys=activity,begin,clock,end,final,first | real fixture sample |
| `signal.trend` | wave | FAIL:ACTION_FAILED | top=summary,meta summary_keys=error,message | real fixture sample |
| `source.context` | none | FAIL:SOURCE_NOT_FOUND | top=meta | repo source file |
| `stream.config.list` | config/list | OK | top=summary,data,meta summary_keys=count data_keys=streams,summary | after stream config load |
| `stream.config.load` | config/list | OK | top=summary,data,meta summary_keys=loaded,mode data_keys=issues,streams,summary | load stream config file |
| `stream.export` | config/list | FAIL:STREAM_NOT_FOUND | top=summary,meta summary_keys=error,message | real fixture sample |
| `stream.query` | config/list | FAIL:STREAM_NOT_FOUND | top=summary,meta summary_keys=error,message | real fixture sample |
| `stream.show` | config/list | FAIL:STREAM_NOT_FOUND | top=summary,meta summary_keys=error,message | real fixture sample |
| `stream.validate` | config/list | FAIL:STREAM_NOT_FOUND | top=summary,meta summary_keys=error,message | real fixture sample |
| `trace.active_driver` | combined | FAIL:SIGNAL_NOT_FOUND | top=summary,meta summary_keys=error | real fixture sample |
| `trace.active_driver_chain` | combined | FAIL:SIGNAL_NOT_FOUND | top=summary,meta summary_keys=error,message | real fixture sample |
| `trace.driver` | design | FAIL:SIGNAL_NOT_FOUND | top=summary,data,meta summary_keys=confidence,confidence_reason,error,has_statement_only,mode,ok data_keys=assignments,confidence,confidence_reason,control_dependencies,dependency_edges,files | real fixture sample |
| `trace.expand` | design | FAIL:SIGNAL_NOT_FOUND | top=summary,data,meta summary_keys=direction,edge_count,node_count,root_signal,truncated data_keys=direction,edge_count,graph,node_count,root_signal | real fixture sample |
| `trace.explain` | design | FAIL:SIGNAL_NOT_FOUND | top=summary,data,meta summary_keys=direction,edge_count,explanation_count,root_signal,skipped_empty_dependency_count,truncated data_keys=direction,edge_count,explanation_count,explanations,root_signal,skipped_empty_dependency_count | real fixture sample |
| `trace.graph` | design | FAIL:SIGNAL_NOT_FOUND | top=summary,data,meta summary_keys=direction,edge_count,node_count,root_signal,truncated data_keys=direction,edge_count,graph,node_count,root_signal | real fixture sample |
| `trace.load` | design | OK | top=summary,data,meta summary_keys=confidence,confidence_reason,has_statement_only,mode,ok,query data_keys=assignments,confidence,confidence_reason,control_dependencies,dependency_edges,files | real fixture sample |
| `trace.path` | design | OK | top=summary,data,meta summary_keys=found,from_signal,path_count,to_signal,truncated data_keys=found,from_signal,path_count,paths,to_signal,truncated | real fixture sample |
| `trace.query` | design | FAIL:SIGNAL_NOT_FOUND | top=summary,data,meta summary_keys=confidence,confidence_reason,error,has_statement_only,mode,ok data_keys=assignments,confidence,confidence_reason,control_dependencies,dependency_edges,files | real fixture sample |
| `value.at` | wave | OK | top=summary,data,meta summary_keys=known,signal,status,time data_keys=known,signal,status,summary,time,value | real fixture sample |
| `value.batch_at` | wave | OK | top=summary,data,meta summary_keys=missing_by_reason,missing_count,signal_count,time,unknown_count,x_or_z_count data_keys=summary,time,values | real fixture sample |
| `verify.conditions` | wave | OK | top=summary,data,meta summary_keys=all_pass,all_passed,condition_count,failed,passed,time data_keys=all_pass,all_passed,checks,condition_count,failed,passed | real fixture sample |
| `window.verify` | wave | FAIL:ACTION_FAILED | top=summary,meta summary_keys=error,message | real fixture sample |

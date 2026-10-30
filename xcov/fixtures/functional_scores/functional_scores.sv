module functional_scores;
  int a;
  int b;
  logic [2:0] select;
  logic [7:0] data [0:2];
  wire [7:0] result [0:3];
  assign result[0] = 8'h12;
  for (genvar m = 0; m < 3; ++m) begin : g_mux
    assign result[m+1] = select[m] ? data[m] : result[m];
  end

  covergroup type_only_cg;
    option.per_instance = 0;
    cp: coverpoint a { bins values[] = {0, 1}; }
  endgroup

  covergroup zero_weight_cg;
    option.per_instance = 1;
    cp: coverpoint b {
      type_option.weight = 0;
      option.weight = 0;
      bins one = {1};
    }
  endgroup

  covergroup empty_cg;
    option.per_instance = 1;
  endgroup

  covergroup weighted_cg;
    option.per_instance = 1;
    hit: coverpoint a {
      type_option.weight = 2;
      option.weight = 3;
      bins zero = {0};
    }
    miss: coverpoint b {
      type_option.weight = 1;
      option.weight = 1;
      bins one = {1};
    }
    zero_weight: coverpoint b {
      type_option.weight = 0;
      option.weight = 0;
      bins one = {1};
    }
  endgroup

  covergroup goals_cg;
    option.per_instance = 1;
    reached: coverpoint a {
      type_option.goal = 50;
      option.goal = 25;
      bins values[] = {0, 1};
    }
    unreached: coverpoint b {
      bins values[] = {1, 2};
    }
  endgroup

  covergroup cross_goals_cg;
    option.per_instance = 1;
    left: coverpoint a { bins values[] = {0, 1}; }
    right: coverpoint b { bins values[] = {0, 1}; }
    pair: cross left, right {
      type_option.weight = 2;
      option.weight = 3;
      type_option.goal = 75;
      option.goal = 50;
    }
  endgroup

  class instances;
    int value;
    covergroup cg;
      option.per_instance = 1;
      cp: coverpoint value { bins values[] = {0, 1}; }
    endgroup
    function new(string name, int weight);
      cg = new();
      cg.set_inst_name(name);
      cg.option.weight = weight;
    endfunction
  endclass

  class merged_instances;
    int value;
    covergroup cg;
      option.per_instance = 1;
      type_option.merge_instances = 1;
      cp: coverpoint value { bins values[] = {0, 1}; }
    endgroup
    function new(string name);
      cg = new();
      cg.set_inst_name(name);
    endfunction
  endclass

  weighted_cg weighted = new();
  goals_cg goals = new();
  cross_goals_cg cross_goals = new();
  type_only_cg type_only = new();
  zero_weight_cg zero_weight_group = new();
  empty_cg empty = new();
  instances first = new("first", 3);
  instances second = new("second", 1);
  merged_instances merged_first = new("merged_first");
  merged_instances merged_second = new("merged_second");

  initial begin
    a = 0;
    b = 0;
    select = 3'b000;
    foreach (data[m]) data[m] = 8'h20 + m;
    weighted.sample();
    goals.sample();
    cross_goals.sample();
    type_only.sample();
    zero_weight_group.sample();
    empty.sample();
    first.value = 0;
    first.cg.sample();
    first.value = 1;
    first.cg.sample();
    second.value = 0;
    second.cg.sample();
    merged_first.value = 0;
    merged_first.cg.sample();
    merged_second.value = 1;
    merged_second.cg.sample();
    #1;
    select = 3'b001;
    #1;
    $finish;
  end
endmodule

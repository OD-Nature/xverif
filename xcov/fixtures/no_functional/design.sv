module code_only;
  bit clk = 0;
  bit reset_n = 0;
  logic [2:0] count = 0;
  always #5 clk = ~clk;
  always @(posedge clk)
    if (!reset_n) count <= 0;
    else count <= count + 1;
  initial begin
    repeat (2) @(negedge clk);
    reset_n = 1;
    repeat (4) @(negedge clk);
    $finish;
  end
endmodule

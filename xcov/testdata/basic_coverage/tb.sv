module xcov_basic_tb;
  logic       clk = 1'b0;
  logic       rst_n = 1'b0;
  logic       enable = 1'b0;
  logic       mode = 1'b0;
  logic [1:0] select = 2'd0;
  logic [3:0] count;
  logic       flag;
  integer     test_mode;

  xcov_basic_dut u_dut (.*);

  always #5 clk = ~clk;

  initial begin
    if (!$value$plusargs("TEST_MODE=%d", test_mode))
      test_mode = 0;
    repeat (2) @(posedge clk);
    rst_n <= 1'b1;
    enable <= 1'b1;
    repeat (8) begin
      @(posedge clk);
      select <= select + 2'd1;
      mode <= test_mode[0];
    end
    if (test_mode != 0) begin
      enable <= 1'b0;
      repeat (2) @(posedge clk);
      enable <= 1'b1;
      repeat (6) @(posedge clk);
    end
    $display("XCOV_BASIC_DONE test_mode=%0d count=%0d flag=%0b", test_mode, count, flag);
    $finish;
  end

endmodule

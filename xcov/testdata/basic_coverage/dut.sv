module xcov_basic_dut (
  input  logic       clk,
  input  logic       rst_n,
  input  logic       enable,
  input  logic       mode,
  input  logic [1:0] select,
  output logic [3:0] count,
  output logic       flag
);

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      count <= 4'h0;
    else if (enable)
      count <= count + 4'h1;
  end

  always_comb begin
    case (select)
      2'd0: flag = count[0];
      2'd1: flag = count[1];
      2'd2: flag = mode ? count[2] : count[3];
      default: flag = 1'b0;
    endcase
  end

endmodule

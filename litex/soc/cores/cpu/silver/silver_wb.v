`timescale 1ns / 1ps

// Wishbone wrapper for Silver (RV64IMAC) when used as a LiteX CPU.
//
// I/D masters are 64-bit, word-addressed. Instruction fetch extracts a 32-bit
// instruction from the 64-bit word; only PC[2:0]==6 && 32-bit insn spans two
// words. Data uses the full 64-bit word plus byte enables.
//
// imem_ready / imem_rdata are combinational on the ACK cycle so the core
// consumes the beat that matches the current PC. A registered ready pulse
// (one cycle late) re-issued the previous PC and, after JAL/branch, delivered
// a stale instruction at the new PC — LiteX then fetched unmapped addresses
// and appeared to hang (bus timeout is 1e6 cycles per access).

module silver_wb #(
    parameter [63:0] RESET_PC = 64'h0000_0000_1000_0000
) (
    input  wire        clk,
    input  wire        rst,

    output wire [28:0] ibus_adr,
    output wire        ibus_cyc,
    output wire        ibus_stb,
    output wire        ibus_we,
    output wire [7:0]  ibus_sel,
    output wire [63:0] ibus_dat_w,
    input  wire [63:0] ibus_dat_r,
    input  wire        ibus_ack,
    input  wire        ibus_err,

    output wire [28:0] dbus_adr,
    output wire        dbus_cyc,
    output wire        dbus_stb,
    output wire        dbus_we,
    output wire [7:0]  dbus_sel,
    output wire [63:0] dbus_dat_w,
    input  wire [63:0] dbus_dat_r,
    input  wire        dbus_ack,
    input  wire        dbus_err,

    output wire        halt_o
);

    wire        rst_n = ~rst;

    wire [63:0] imem_addr;
    wire        imem_req;
    reg  [31:0] imem_rdata;
    reg         imem_ready;

    wire [63:0] dmem_addr;
    wire        dmem_req;
    wire        dmem_we;
    wire [2:0]  dmem_funct3;
    wire [63:0] dmem_wdata;
    wire        dmem_ready;

    riscv_rtype_fsm #(
        .RESET_PC     (RESET_PC),
        .EXTERNAL_MEM (1)
    ) u_core (
        .clk            (clk),
        .rst_n          (rst_n),
        .state_o        (),
        .pc_o           (),
        .instr_o        (),
        .alu_result_o   (),
        .halt_o         (halt_o),
        .wb_valid_o     (),
        .ecall_o        (),
        .ebreak_o       (),
        .dbg_addr       (5'd0),
        .dbg_rdata      (),
        .dbg_dmem_addr  (4'd0),
        .dbg_dmem_rdata (),
        .imem_addr_o    (imem_addr),
        .imem_req_o     (imem_req),
        .imem_rdata_i   (imem_rdata),
        .imem_ready_i   (imem_ready),
        .dmem_addr_o    (dmem_addr),
        .dmem_req_o     (dmem_req),
        .dmem_we_o      (dmem_we),
        .dmem_funct3_o  (dmem_funct3),
        .dmem_wdata_o   (dmem_wdata),
        .dmem_rdata_i   (dbus_dat_r),
        .dmem_ready_i   (dmem_ready)
    );

    // ------------------------------------------------------------------
    // Instruction fetch
    // ------------------------------------------------------------------
    localparam IF_IDLE = 2'd0;
    localparam IF_W0   = 2'd1;
    localparam IF_W1   = 2'd2;

    reg  [1:0]  if_state;
    reg  [28:0] if_adr;
    reg         if_cyc;
    reg  [15:0] if_half;
    reg  [63:0] if_pc;

    wire        ibus_done = ibus_ack | ibus_err;
    wire        if_kill   = (if_state != IF_IDLE) && (imem_addr[31:1] != if_pc[31:1]);
    wire        if_span   = (if_pc[2:1] == 2'b11) && (ibus_dat_r[49:48] == 2'b11);

    assign ibus_adr   = if_adr;
    assign ibus_cyc   = if_cyc;
    assign ibus_stb   = if_cyc;
    assign ibus_we    = 1'b0;
    assign ibus_sel   = 8'hFF;
    assign ibus_dat_w = 64'd0;

    // Same-cycle ACK → ready, using the latched fetch PC (not the live pc,
    // which may already be a redirect target).
    always @(*) begin
        imem_rdata = 32'd0;
        imem_ready = 1'b0;
        if (!if_kill && ibus_done) begin
            if (if_state == IF_W0) begin
                case (if_pc[2:1])
                    2'b00: begin
                        imem_rdata = ibus_dat_r[31:0];
                        imem_ready = 1'b1;
                    end
                    2'b01: begin
                        imem_rdata = ibus_dat_r[47:16];
                        imem_ready = 1'b1;
                    end
                    2'b10: begin
                        imem_rdata = ibus_dat_r[63:32];
                        imem_ready = 1'b1;
                    end
                    default: begin
                        if (!if_span) begin
                            imem_rdata = {16'd0, ibus_dat_r[63:48]};
                            imem_ready = 1'b1;
                        end
                    end
                endcase
            end else if (if_state == IF_W1) begin
                imem_rdata = {ibus_dat_r[15:0], if_half};
                imem_ready = 1'b1;
            end
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            if_state <= IF_IDLE;
            if_adr   <= 29'd0;
            if_cyc   <= 1'b0;
            if_half  <= 16'd0;
            if_pc    <= 64'd0;
        end else begin
            case (if_state)
                IF_IDLE: begin
                    if (imem_req) begin
                        if_pc    <= imem_addr;
                        if_adr   <= imem_addr[31:3];
                        if_cyc   <= 1'b1;
                        if_state <= IF_W0;
                    end
                end
                IF_W0: begin
                    if (if_kill) begin
                        if_cyc   <= 1'b0;
                        if_state <= IF_IDLE;
                    end else if (ibus_done) begin
                        if (if_span) begin
                            if_half  <= ibus_dat_r[63:48];
                            if_adr   <= if_pc[31:3] + 29'd1;
                            if_state <= IF_W1;
                        end else begin
                            if_cyc   <= 1'b0;
                            if_state <= IF_IDLE;
                        end
                    end
                end
                IF_W1: begin
                    if (if_kill) begin
                        if_cyc   <= 1'b0;
                        if_state <= IF_IDLE;
                    end else if (ibus_done) begin
                        if_cyc   <= 1'b0;
                        if_state <= IF_IDLE;
                    end
                end
                default: begin
                    if_cyc   <= 1'b0;
                    if_state <= IF_IDLE;
                end
            endcase
        end
    end

    // ------------------------------------------------------------------
    // Data bus (registered request so adr/sel/we stay still until ACK)
    // ------------------------------------------------------------------
    reg        d_cyc;
    reg [28:0] d_adr;
    reg        d_we;
    reg [7:0]  d_sel_r;
    reg [63:0] d_dat_w_r;

    reg [7:0]  d_sel;
    reg [63:0] d_dat_w;

    always @(*) begin
        d_sel   = 8'hFF;
        d_dat_w = dmem_wdata << (8 * dmem_addr[2:0]);
        case (dmem_funct3)
            3'b000: d_sel = 8'b0000_0001 << dmem_addr[2:0];
            3'b001: d_sel = 8'b0000_0011 << dmem_addr[2:0];
            3'b010: d_sel = 8'b0000_1111 << dmem_addr[2:0];
            3'b011: d_sel = 8'hFF;
            default: d_sel = 8'hFF;
        endcase
    end

    wire dbus_done = dbus_ack | dbus_err;

    assign dbus_adr   = d_adr;
    assign dbus_cyc   = d_cyc;
    assign dbus_stb   = d_cyc;
    assign dbus_we    = d_we;
    assign dbus_sel   = d_sel_r;
    assign dbus_dat_w = d_dat_w_r;
    assign dmem_ready = d_cyc & dbus_done;

    always @(posedge clk) begin
        if (rst) begin
            d_cyc    <= 1'b0;
            d_adr    <= 29'd0;
            d_we     <= 1'b0;
            d_sel_r  <= 8'd0;
            d_dat_w_r<= 64'd0;
        end else if (d_cyc) begin
            if (dbus_done)
                d_cyc <= 1'b0;
        end else if (dmem_req) begin
            d_cyc     <= 1'b1;
            d_adr     <= dmem_addr[31:3];
            d_we      <= dmem_we;
            d_sel_r   <= d_sel;
            d_dat_w_r <= d_dat_w;
        end
    end

endmodule

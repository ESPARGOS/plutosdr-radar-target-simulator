#!/usr/bin/env python3
"""Generate the two interpolation filters used by the standard-rate FPGA.

A fixed 95-tap half-band interpolator doubles 61.44 MSa/s to 122.88 MSa/s.
The eight-tap fractional-delay filter then covers the full 56 MHz signal band.
The fixed coefficients are a symmetric equiripple fit with a 28 MHz passband
and 33.44 MHz stopband at 122.88 MSa/s, rounded to Q1.17 with unity DC gain.
Only its 24 independent nonzero coefficients are listed below.
"""
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def halfband():
    independent = np.array([-51, 62, -98, 148, -213, 297, -404, 537, -702, 903, -1146, 1440, -1795, 2222, -2740, 3373, -4162, 5169, -6501, 8366, -11206, 16175, -27511, 83373], dtype=np.int64)
    result = np.zeros(95, dtype=np.int64)
    result[::2] = np.r_[independent, independent[::-1]]
    result[47] = 131072
    return result


def fractional():
    omega = 2 * np.pi * np.linspace(0, 28e6, 1025) / 122.88e6
    basis = np.exp(-1j * omega[:, None] * np.arange(8))
    center = 3
    other = [k for k in range(8) if k != center]
    a = basis[:, other] - basis[:, center, None]
    mu = np.arange(1024) / 1024
    b = np.exp(-1j * omega[:, None] * (center + mu)) - basis[:, center, None]
    fitted = np.linalg.lstsq(np.vstack((a.real, a.imag)),
                           np.vstack((b.real, b.imag)), rcond=None)[0]
    result = np.empty((8, 1024))
    result[other] = fitted
    result[center] = 1 - fitted.sum(axis=0)
    words = np.rint(result.T * 65536).astype(np.int64)
    words[:, center] += 65536 - words.sum(axis=1)
    return words

def generate_upsampler():
    h = halfband()[::2]
    assert len(h)==48 and np.array_equal(h,h[::-1])
    assert abs(h).sum()/131072 < 4
    s=['module standard_upsample(input wire clk, reset, valid, input wire [23:0] sample,',
       'output wire [31:0] direct_sample, interpolated_sample, output wire output_valid);',
       'reg [8:0] valid_pipe;',
       'always @(posedge clk) valid_pipe <= reset ? 0 : {valid_pipe[7:0],valid};',
       'assign output_valid = valid_pipe[8];']
    for iq in range(2):
        s += [f'reg signed [11:0] history{iq}[0:46];',
              f'wire signed [11:0] x{iq} = sample[{12*iq}+:12];',
              f'reg signed [15:0] direct{iq}[0:8];',
              f'always @(posedge clk) begin',
              f'if(reset) begin for(integer k=0;k<47;k=k+1) history{iq}[k]<=0; end',
              f'else if(valid) begin history{iq}[0]<=x{iq}; for(integer k=1;k<47;k=k+1) history{iq}[k]<=history{iq}[k-1]; end',
              f'direct{iq}[0] <= $signed(history{iq}[22]) <<< 2;',
              f'for(integer k=1;k<9;k=k+1) direct{iq}[k] <= direct{iq}[k-1];',
              'end',f'assign direct_sample[{iq*16}+:16]=direct{iq}[8];']
        for k in range(24):
            a=f'x{iq}' if k==0 else f'history{iq}[{k-1}]'
            b=f'history{iq}[{46-k}]'
            c=int(h[k]); constant=f"{'-' if c<0 else ''}18'sd{abs(c)}"
            s += [f'reg signed [12:0] pair{iq}_{k};',
                  f'(* use_dsp="yes" *) reg signed [30:0] prod{iq}_{k};',
                  f'reg signed [30:0] delayed{iq}_{k};',
                  f'always @(posedge clk) begin pair{iq}_{k} <= $signed({a})+$signed({b}); prod{iq}_{k}<=pair{iq}_{k}*{constant}; delayed{iq}_{k}<=prod{iq}_{k}; end']
        nodes=[f'delayed{iq}_{k}' for k in range(24)]
        stage=0
        while len(nodes)>1:
            nxt=[]
            for k in range(0,len(nodes),2):
                v=f'sum{iq}_{stage}_{k//2}'; terms=nodes[k]
                if k+1<len(nodes): terms+=' + '+nodes[k+1]
                s += [f'(* use_dsp="no" *) reg signed [35:0] {v};',f'always @(posedge clk) {v}<={terms};']
                nxt.append(v)
            nodes=nxt;stage+=1
        s += [f'wire signed [35:0] rounded{iq}={nodes[0]}+36\'sd16384;',
              f'reg [15:0] output{iq};', f'always @(posedge clk) output{iq} <= rounded{iq} >>> 15;', f'assign interpolated_sample[{iq*16}+:16] = output{iq};']
    s.append('endmodule')
    (ROOT/'rtl/standard_upsample.sv').write_text('\n'.join(s)+'\n')


def generate_fractional():
    h = fractional()
    s=['module standard_fir(input wire clk, input wire [255:0] samples, input wire [9:0] fraction, output wire [75:0] result);',
       '(* ram_style="block" *) reg [143:0] memory[0:1023];','reg [143:0] data, coefficients;',
       'reg [255:0] sample_pipe0, sample_pipe1;', 'initial begin']
    for n,row in enumerate(h):
     word=sum((int(c)&262143)<<(18*k) for k,c in enumerate(row))
     s.append(f"memory[{n}]=144'h{word:036x};")
    s+=['end','always @(posedge clk) begin data<=memory[fraction]; coefficients<=data; sample_pipe0<=samples; sample_pipe1<=sample_pipe0; end']
    for iq in range(2):
     for k in range(8):
      s += [f'reg signed [15:0] x{iq}_{k};',f'reg signed [17:0] h{iq}_{k};',
            f'(* use_dsp="yes" *) reg signed [33:0] p{iq}_{k};',f'reg signed [33:0] d{iq}_{k};',
            f'always @(posedge clk) begin x{iq}_{k}<=sample_pipe1[{32*k+16*iq}+:16]; h{iq}_{k}<=coefficients[{18*k}+:18]; p{iq}_{k}<=x{iq}_{k}*h{iq}_{k}; d{iq}_{k}<=p{iq}_{k}; end']
     nodes=[f'd{iq}_{k}' for k in range(8)]
     for stage in range(3):
      nxt=[]
      for k in range(0,len(nodes),2):
       v=f's{iq}_{stage}_{k//2}'; width=35+stage
       s += [f'(* use_dsp="no" *) reg signed [{width-1}:0] {v};',f'always @(posedge clk) {v}<=$signed({nodes[k]})+$signed({nodes[k+1]});']
       nxt.append(v)
      nodes=nxt
     s.append(f'assign result[{38*iq}+:38]=$signed({nodes[0]});')
    s.append('endmodule')
    (ROOT/'rtl/standard_fir.sv').write_text('\n'.join(s)+'\n')


if __name__ == "__main__":
    generate_upsampler()
    generate_fractional()

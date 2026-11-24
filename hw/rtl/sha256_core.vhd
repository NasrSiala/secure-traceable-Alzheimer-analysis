-- sha256_core: SHA-256 compression function for blocks that are already padded (T3.18, 1/2).
--
-- FIPS 180-4, one round per clock cycle, the message schedule in a shift register of 16 words
-- (ADR-12, Architecture 5.6). It does no padding: the padder (T3.18, 2/2) and the AXI wrapper
-- (T3.20) come around it. The constants K and H_INIT below are written by a script from the roots
-- of the first primes and checked against FIPS 180-4 by tests/scripts/test_sha256_core.py.
--
-- Interface (one clock `aclk`, synchronous active-low reset `aresetn`, as everywhere in hw/rtl):
--   init        1 cycle: start a new message (H := H0, done := 0). Taken whenever the core is not
--               busy; do not raise it in the cycle of a word.
--   word_valid  a 32-bit word is offered, taken when word_valid and word_ready are both 1.
--   word_data   the word, big-endian: the first byte of the block in bits 31..24.
--   word_ready  1 while the core waits for words (not busy, and init is low).
--   busy        1 from the cycle after the 16th word until the digest is updated.
--   done        1 once a block is compressed; cleared by init or by the next word.
--   digest      H0 .. H7, H0 in bits 255..224: read as hexadecimal it is hashlib's hexdigest().
--
-- A block is 16 words (16 cycles with a word each cycle), then 64 round cycles and one cycle to add
-- the working variables to H. `busy` stays high for those 65 cycles. `done` rises on the edge that
-- leaves the add state: the testbench counts that as 66 cycles after the edge that took the 16th
-- word. For a message of several blocks, send the blocks one after the other
-- without `init`: H chains from block to block. After `done`, `init` (or the first word of the next
-- block) is accepted at once.
--
-- Conventions: VHDL-2008, ieee.numeric_std only, one clock, no vendor primitive.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity sha256_core is
  port (
    aclk       : in  std_logic;
    aresetn    : in  std_logic;
    init       : in  std_logic;
    word_valid : in  std_logic;
    word_data  : in  std_logic_vector(31 downto 0);
    word_ready : out std_logic;
    busy       : out std_logic;
    done       : out std_logic;
    digest     : out std_logic_vector(255 downto 0)
  );
end entity sha256_core;

architecture rtl of sha256_core is
  subtype word_t is unsigned(31 downto 0);
  type word_array_t is array (natural range <>) of word_t;

  -- FIPS 180-4 4.2.2: the first 32 bits of the fractional parts of the cube roots of the first 64
  -- primes.
  constant K : word_array_t(0 to 63) := (
    x"428a2f98", x"71374491", x"b5c0fbcf", x"e9b5dba5",
    x"3956c25b", x"59f111f1", x"923f82a4", x"ab1c5ed5",
    x"d807aa98", x"12835b01", x"243185be", x"550c7dc3",
    x"72be5d74", x"80deb1fe", x"9bdc06a7", x"c19bf174",
    x"e49b69c1", x"efbe4786", x"0fc19dc6", x"240ca1cc",
    x"2de92c6f", x"4a7484aa", x"5cb0a9dc", x"76f988da",
    x"983e5152", x"a831c66d", x"b00327c8", x"bf597fc7",
    x"c6e00bf3", x"d5a79147", x"06ca6351", x"14292967",
    x"27b70a85", x"2e1b2138", x"4d2c6dfc", x"53380d13",
    x"650a7354", x"766a0abb", x"81c2c92e", x"92722c85",
    x"a2bfe8a1", x"a81a664b", x"c24b8b70", x"c76c51a3",
    x"d192e819", x"d6990624", x"f40e3585", x"106aa070",
    x"19a4c116", x"1e376c08", x"2748774c", x"34b0bcb5",
    x"391c0cb3", x"4ed8aa4a", x"5b9cca4f", x"682e6ff3",
    x"748f82ee", x"78a5636f", x"84c87814", x"8cc70208",
    x"90befffa", x"a4506ceb", x"bef9a3f7", x"c67178f2"
  );

  -- FIPS 180-4 5.3.3: the first 32 bits of the fractional parts of the square roots of the first 8
  -- primes.
  constant H_INIT : word_array_t(0 to 7) := (
    x"6a09e667", x"bb67ae85", x"3c6ef372", x"a54ff53a",
    x"510e527f", x"9b05688c", x"1f83d9ab", x"5be0cd19"
  );

  type state_t is (S_LOAD, S_ROUNDS, S_ADD);

  signal state : state_t;
  signal count : unsigned(5 downto 0);
  signal w     : word_array_t(0 to 15);
  signal h     : word_array_t(0 to 7);
  signal va, vb, vc, vd, ve, vf, vg, vh : word_t;
  signal done_r : std_logic;

  function big_sigma0 (x : word_t) return word_t is
  begin
    return rotate_right(x, 2) xor rotate_right(x, 13) xor rotate_right(x, 22);
  end function;

  function big_sigma1 (x : word_t) return word_t is
  begin
    return rotate_right(x, 6) xor rotate_right(x, 11) xor rotate_right(x, 25);
  end function;

  function small_sigma0 (x : word_t) return word_t is
  begin
    return rotate_right(x, 7) xor rotate_right(x, 18) xor shift_right(x, 3);
  end function;

  function small_sigma1 (x : word_t) return word_t is
  begin
    return rotate_right(x, 17) xor rotate_right(x, 19) xor shift_right(x, 10);
  end function;

  function choose (x, y, z : word_t) return word_t is
  begin
    return (x and y) xor ((not x) and z);
  end function;

  function majority (x, y, z : word_t) return word_t is
  begin
    return (x and y) xor (x and z) xor (y and z);
  end function;
begin
  word_ready <= '1' when state = S_LOAD and init = '0' else '0';
  busy       <= '0' when state = S_LOAD else '1';
  done       <= done_r;

  digest <= std_logic_vector(h(0)) & std_logic_vector(h(1)) & std_logic_vector(h(2)) &
            std_logic_vector(h(3)) & std_logic_vector(h(4)) & std_logic_vector(h(5)) &
            std_logic_vector(h(6)) & std_logic_vector(h(7));

  process (aclk)
    variable t1, t2, w_next : word_t;
  begin
    if rising_edge(aclk) then
      if aresetn = '0' then
        state  <= S_LOAD;
        count  <= (others => '0');
        done_r <= '0';
        h      <= H_INIT;
        w      <= (others => (others => '0'));
        va <= (others => '0'); vb <= (others => '0'); vc <= (others => '0');
        vd <= (others => '0'); ve <= (others => '0'); vf <= (others => '0');
        vg <= (others => '0'); vh <= (others => '0');
      else
        case state is
          when S_LOAD =>
            if init = '1' then
              h      <= H_INIT;
              done_r <= '0';
              count  <= (others => '0');
            elsif word_valid = '1' then
              -- The first word of the block ends in w(0) after the sixteenth shift.
              for i in 0 to 14 loop
                w(i) <= w(i + 1);
              end loop;
              w(15)  <= unsigned(word_data);
              done_r <= '0';
              if count = 15 then
                count <= (others => '0');
                state <= S_ROUNDS;
                va <= h(0); vb <= h(1); vc <= h(2); vd <= h(3);
                ve <= h(4); vf <= h(5); vg <= h(6); vh <= h(7);
              else
                count <= count + 1;
              end if;
            end if;

          when S_ROUNDS =>
            -- Round t uses W[t] = w(0); the word shifted in is W[t + 16].
            w_next := small_sigma1(w(14)) + w(9) + small_sigma0(w(1)) + w(0);
            t1 := vh + big_sigma1(ve) + choose(ve, vf, vg) + K(to_integer(count)) + w(0);
            t2 := big_sigma0(va) + majority(va, vb, vc);
            vh <= vg;
            vg <= vf;
            vf <= ve;
            ve <= vd + t1;
            vd <= vc;
            vc <= vb;
            vb <= va;
            va <= t1 + t2;
            for i in 0 to 14 loop
              w(i) <= w(i + 1);
            end loop;
            w(15) <= w_next;
            if count = 63 then
              count <= (others => '0');
              state <= S_ADD;
            else
              count <= count + 1;
            end if;

          when S_ADD =>
            h(0) <= h(0) + va;
            h(1) <= h(1) + vb;
            h(2) <= h(2) + vc;
            h(3) <= h(3) + vd;
            h(4) <= h(4) + ve;
            h(5) <= h(5) + vf;
            h(6) <= h(6) + vg;
            h(7) <= h(7) + vh;
            done_r <= '1';
            state  <= S_LOAD;
        end case;
      end if;
    end if;
  end process;
end architecture rtl;

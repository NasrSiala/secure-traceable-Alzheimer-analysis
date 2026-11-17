-- Module de simulation T1.10 ; aucun cœur SHA-256/FIR ni primitive constructeur.
library ieee;
use ieee.std_logic_1164.all;

entity ci_register is
    port (
        clk     : in  std_logic;
        aresetn : in  std_logic;
        d       : in  std_logic_vector(7 downto 0);
        q       : out std_logic_vector(7 downto 0)
    );
end entity;

architecture rtl of ci_register is
begin
    process (clk, aresetn)
    begin
        if aresetn = '0' then
            q <= (others => '0');
        elsif rising_edge(clk) then
            q <= not d;
        end if;
    end process;
end architecture;

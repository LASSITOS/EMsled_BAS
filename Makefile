
TGT=arm
PRU_INC=/usr/include 
PRU_LIB=/usr/lib
PASM=/home/root/AM335x_PRU_BeagleBone/GPIO_PWM_PRU/utils/pasm
PASM=pasm

all	:
	echo target is $(TGT)
ifeq ($(TGT),arm)
	make $(TGT)/pru00.bin
	make $(TGT)/pru01.bin
	make $(TGT)/spi_awg.bin
endif

$(TGT)/pru00.bin : pru00.p pructl.h pru.hp | $(TGT)
	${PASM} -V3 -b pru00.p
	mv pru00.bin $(TGT)/pru00.bin
$(TGT)/spi_awg.bin : spi_awg.p pructl.h pru.hp | $(TGT)
	${PASM} -V3 -b spi_awg.p
	mv spi_awg.bin $(TGT)/spi_awg.bin

$(TGT)/pru01.bin : pru01.p pructl.h pru.hp | $(TGT)
	${PASM} -V3 -b pru01.p
	mv pru01.bin $(TGT)/pru01.bin


clean	:
	rm -f $(TGT)/*
	rm -rf $(TGT)
	rm -f *~
	rm -f tmp

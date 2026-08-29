本项目的目的是实现一个通用的uvm agent，我称之为xif_agent，x代表cross，未知，if代表interface。

agent需要满足以下功能
## xif_agent包成一个xif_agent_pkg


## 统一的xact控制
1. xif_xact作为xif_agent的全局配置，agent、interface、montior、driver内都需要保存同一个对象
2. 传递方式由agent在build phase获取，然后传递assign到其他组件中
3. xif_xact需要配置有以下开关

- 一个enum控制agent模式，active或者only_montior
- 一个enum控制driver的模式，master还是slave
- 一个enum控制接口使用rdy还是bp还是两者都不使用
- 一个enum控制bp、rdy反压的模式

## 同时支持master和slave
1. master时，driver 需要控制vld、pd信号
2. slave时，driver  需要支持控制rdy或者bp信号

## 支持通用的interface驱动

- interface内除了包含clk，rst，vld、rdy、bp信号，pd信号是以参数类型的方式声明的
- pd的类型为struct类型的信号，其内部由用户定义对应的logic类型信号
- interface内部需要有mon_cb和drv_cb
- 在interface内增加sva检查，当vld有效时，检查vld时，pb是否出现未知值，否则报uvm_error
- always块统计，在使用rdy或者bp时，若vld为1，rdy、bp根据选择检查，超过xact中配置的超时clk数时，报uvm_error
- 根据xact中配置的bp、rdy反压的模式，驱动bp和rdy，如果为normal，则在short、long、pluse、random四种模式中，以xact中配置的周期数为单位，每次随机一个。如果为short、long、pluse、random，则整个仿真过程中全程使用对应的模式。其中short时反压1-10拍，三段式随机，long时反压10-100拍，三段式随机，这两个模式的max和min都支持xact配置。pluse支持配置多少个周期拉高一次，默认1拍。如果为rls，则全程不反压。
- 包含一个set_bp task，参数为一个字符串，如果是字符串是close，则force bp或者rdy为对应值，关闭通道，如果字符串是open，则force bp或者rdy为对应值保持通道使用不反压
- 用FCOV_ON宏保护隔离起来，收集握手的覆盖率，包括vld多久才握手成功，连续多少拍握手都成功


## 参数化pd
pd作为参数，agent driver montior interface都是参数化的

## driver
最简化设计，直接接受port拿到的xif_item，把xif_item中的pd，驱动到接口上，每一拍都try get，没get到则这一拍，随机驱动pd为x、1、0、z。如果get到了，则根据item中的leading_num，在leading_num拍后驱动到pd上，在握手成功后（如果不使用bp或者rdy则没有这一步）然后根据item中post_num，在post_num个clk后，在继续try_get。除了驱动拍，剩下的时候pd保持在x 1 0 z随机。驱动时始终@drv_cb，并且使用非阻塞赋值

## monitor
根据xact配置，检测接口，产生对应的xif_item，通过uvm_analysis_port发出去。采用时使用@mon_cb,使用阻塞赋值采样。

## sequencer
只用于链接driver


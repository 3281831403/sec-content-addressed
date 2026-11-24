内容寻址的备份库被换掉一个分块，整体校验值却没变，恢复出来是错的：分块摘要缺少块长前缀，移动边界后不同切分可以拼出同一摘要；整体摘要只累加各块摘要的长度而不把摘要内容纳入计算，等长替换不会改变根；整体摘要不按块序合成，交换相邻块的摘要仍得到同一个根；空输入返回空串而不是约定的空根常量，空内容与缺少根无法区分；写入时不做内容去重，同一内容重复落盘却只把对象引用计数加一；取回时跳过逐块摘要校验，被替换的分块会原样拼进恢复结果；校验发现损坏后仍继续扫描，最终报告最后一个损坏块而不是最先损坏的块；删除时不检查剩余引用计数，只要调用删除就移除对象和共享分块；最后一块不按短块单独处理，先补齐到固定长度再计算摘要导致尾块失配；批量操作复用上一操作的存储游标，第二个操作从第一个操作停留的位置继续。cas/_impl.py 是核心，tests/test_store.py 15个红。要修的是：按上面的顺序把 10 个缺陷逐个修掉。

运行方式
========

在仓库根目录执行：

    python -m pytest tests -q

当前基线必须恰好为 15 failed，且没有 error。修复全部缺陷后应当为 15 passed。

字段表
======

安全 / 漏洞检测与攻防 / Bugfix / Python 3, pytest / 无外部依赖

| 字段 | 取值 |
| --- | --- |
| 所属领域 | 安全 |
| 子方向 | 漏洞检测与攻防 |
| 任务类型 | Bugfix |
| 语言/框架 | Python 3, pytest |
| 环境可复现等级 | 无外部依赖 |

tests 不可修改
==============

tests/test_store.py 是判分入口，不得修改。也不得通过修改测试、跳过测试、放宽断言的方式制造通过。

门面布局
========

sec-content-addressed/
    README.md
    conftest.py
    cas/
        __init__.py
        _impl.py
        api.py
    tests/
        test_store.py

cas/__init__.py 只从 cas.api 导出。
cas/api.py 只做再导出。
cas/_impl.py 是唯一实现文件，恰好 8 个函数桩，全部 raise NotImplementedError。
tests/test_store.py 恰好 15 个测试。

存储约定
========

store 是普通字典：chunks 把分块摘要映射到 data 字节与 refs 计数；objects 把整体摘要映射到有序 digests、lengths、size 与 refs。put 默认按 8 字节分块，相同内容只保留一份分块并增加引用。get 只有在逐块摘要和有序整体根都通过后才拼接返回。verify 返回 ok 与首个损坏块的 bad_index。drop 返回剩余引用数，归零时才移除对象与不再被引用的分块。cas_batch 的每个 op 是带 op、store 以及 data 或 root 的字典，policy 支持 stop_on_error；各 op 使用各自的存储游标。

修复顺序
========

按题面列出的 10 个缺陷顺序逐个修掉，不要改变公开函数签名，不要增加外部依赖。
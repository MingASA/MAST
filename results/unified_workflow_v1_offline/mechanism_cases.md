# 机制案例

## active / autonomous
错误完成 0/4；错误触达组织 0；恢复 0；查证 0。
检测记录：`[]`
停止原因：`[]`

## active / root_gate
错误完成 0/4；错误触达组织 0；恢复 0；查证 22。
检测记录：`[]`
停止原因：`[]`

## active / simple_dependency_gate
错误完成 0/4；错误触达组织 0；恢复 0；查证 42。
检测记录：`[]`
停止原因：`[]`

## active / dependency
错误完成 0/4；错误触达组织 0；恢复 0；查证 42。
检测记录：`[]`
停止原因：`[]`

## active / dependency_push
错误完成 0/4；错误触达组织 0；恢复 0；查证 42。
检测记录：`[]`
停止原因：`[]`

## active / verify_all
错误完成 0/4；错误触达组织 0；恢复 0；查证 42。
检测记录：`[]`
停止原因：`[]`

## active / selective
错误完成 0/4；错误触达组织 0；恢复 0；查证 16。
检测记录：`[]`
停止原因：`[]`

## active / recovery_ablation
错误完成 0/4；错误触达组织 0；恢复 0；查证 42。
检测记录：`[]`
停止原因：`[]`

## root_retraction / autonomous
错误完成 2/4；错误触达组织 2；恢复 0；查证 0。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "retraction", "origin": "source", "first_consumer_detection_delay": null, "issuer_detected_tick": 10, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## root_retraction / root_gate
错误完成 0/4；错误触达组织 0；恢复 2；查证 22。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "retraction", "origin": "source", "first_consumer_detection_delay": 2, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 12, "middle_b": 12, "receiver_a": 20, "receiver_b": 20}}]`
停止原因：`[]`

## root_retraction / simple_dependency_gate
错误完成 0/4；错误触达组织 0；恢复 2；查证 42。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "retraction", "origin": "source", "first_consumer_detection_delay": 2, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 12, "middle_b": 12, "receiver_a": 20, "receiver_b": 20}}]`
停止原因：`[]`

## root_retraction / dependency
错误完成 0/4；错误触达组织 0；恢复 2；查证 42。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "retraction", "origin": "source", "first_consumer_detection_delay": 2, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 12, "middle_b": 12, "receiver_a": 20, "receiver_b": 20}}]`
停止原因：`[]`

## root_retraction / dependency_push
错误完成 0/4；错误触达组织 0；恢复 2；查证 36。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "retraction", "origin": "source", "first_consumer_detection_delay": 1, "issuer_detected_tick": 10, "consumer_detection_ticks": {"coordinator": 11, "middle_b": 12, "middle_a": 12, "receiver_a": 20, "receiver_b": 20}}]`
停止原因：`[]`

## root_retraction / verify_all
错误完成 0/4；错误触达组织 0；恢复 2；查证 42。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "retraction", "origin": "source", "first_consumer_detection_delay": 2, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 12, "middle_b": 12, "receiver_a": 20, "receiver_b": 20}}]`
停止原因：`[]`

## root_retraction / selective
错误完成 0/4；错误触达组织 2；恢复 2；查证 24。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "retraction", "origin": "source", "first_consumer_detection_delay": 4, "issuer_detected_tick": 10, "consumer_detection_ticks": {"receiver_a": 14, "receiver_b": 14}}]`
停止原因：`[]`

## root_retraction / recovery_ablation
错误完成 0/4；错误触达组织 0；恢复 2；查证 36。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "retraction", "origin": "source", "first_consumer_detection_delay": 1, "issuer_detected_tick": 10, "consumer_detection_ticks": {"coordinator": 11, "middle_b": 12, "middle_a": 12, "receiver_a": 20, "receiver_b": 20}}]`
停止原因：`[]`

## intermediate_retraction / autonomous
错误完成 2/4；错误触达组织 2；恢复 0；查证 0。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 10, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## intermediate_retraction / root_gate
错误完成 2/4；错误触达组织 2；恢复 0；查证 22。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 10, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## intermediate_retraction / simple_dependency_gate
错误完成 0/4；错误触达组织 0；恢复 2；查证 38。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 2, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 12, "middle_b": 12, "receiver_a": 20, "receiver_b": 20}}]`
停止原因：`[]`

## intermediate_retraction / dependency
错误完成 0/4；错误触达组织 0；恢复 2；查证 38。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 2, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 12, "middle_b": 12, "receiver_a": 20, "receiver_b": 20}}]`
停止原因：`[]`

## intermediate_retraction / dependency_push
错误完成 0/4；错误触达组织 0；恢复 2；查证 36。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 1, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 11, "middle_b": 11, "receiver_a": 20, "receiver_b": 20}}]`
停止原因：`[]`

## intermediate_retraction / verify_all
错误完成 0/4；错误触达组织 0；恢复 2；查证 38。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 2, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 12, "middle_b": 12, "receiver_a": 20, "receiver_b": 20}}]`
停止原因：`[]`

## intermediate_retraction / selective
错误完成 0/4；错误触达组织 2；恢复 2；查证 18。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 4, "issuer_detected_tick": 10, "consumer_detection_ticks": {"receiver_a": 14, "receiver_b": 14}}]`
停止原因：`[]`

## intermediate_retraction / recovery_ablation
错误完成 0/4；错误触达组织 0；恢复 2；查证 36。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 1, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 11, "middle_b": 11, "receiver_a": 20, "receiver_b": 20}}]`
停止原因：`[]`

## branch_retraction / autonomous
错误完成 0/4；错误触达组织 0；恢复 1；查证 0。
检测记录：`[{"target": "60a2403c78be1bcac7eb376afa0d067be8c496ec217253136530ffba2fc20e02", "kind": "retraction", "origin": "middle_a", "first_consumer_detection_delay": 10, "issuer_detected_tick": 10, "consumer_detection_ticks": {"receiver_a": 20}}]`
停止原因：`[]`

## branch_retraction / root_gate
错误完成 0/4；错误触达组织 0；恢复 1；查证 21。
检测记录：`[{"target": "60a2403c78be1bcac7eb376afa0d067be8c496ec217253136530ffba2fc20e02", "kind": "retraction", "origin": "middle_a", "first_consumer_detection_delay": 10, "issuer_detected_tick": 10, "consumer_detection_ticks": {"receiver_a": 20}}]`
停止原因：`[]`

## branch_retraction / simple_dependency_gate
错误完成 0/4；错误触达组织 0；恢复 1；查证 39。
检测记录：`[{"target": "60a2403c78be1bcac7eb376afa0d067be8c496ec217253136530ffba2fc20e02", "kind": "retraction", "origin": "middle_a", "first_consumer_detection_delay": 10, "issuer_detected_tick": 10, "consumer_detection_ticks": {"receiver_a": 20}}]`
停止原因：`[]`

## branch_retraction / dependency
错误完成 0/4；错误触达组织 0；恢复 1；查证 39。
检测记录：`[{"target": "60a2403c78be1bcac7eb376afa0d067be8c496ec217253136530ffba2fc20e02", "kind": "retraction", "origin": "middle_a", "first_consumer_detection_delay": 10, "issuer_detected_tick": 10, "consumer_detection_ticks": {"receiver_a": 20}}]`
停止原因：`[]`

## branch_retraction / dependency_push
错误完成 0/4；错误触达组织 0；恢复 1；查证 39。
检测记录：`[{"target": "60a2403c78be1bcac7eb376afa0d067be8c496ec217253136530ffba2fc20e02", "kind": "retraction", "origin": "middle_a", "first_consumer_detection_delay": 10, "issuer_detected_tick": 10, "consumer_detection_ticks": {"receiver_a": 20}}]`
停止原因：`[]`

## branch_retraction / verify_all
错误完成 0/4；错误触达组织 0；恢复 1；查证 39。
检测记录：`[{"target": "60a2403c78be1bcac7eb376afa0d067be8c496ec217253136530ffba2fc20e02", "kind": "retraction", "origin": "middle_a", "first_consumer_detection_delay": 10, "issuer_detected_tick": 10, "consumer_detection_ticks": {"receiver_a": 20}}]`
停止原因：`[]`

## branch_retraction / selective
错误完成 0/4；错误触达组织 0；恢复 1；查证 16。
检测记录：`[{"target": "60a2403c78be1bcac7eb376afa0d067be8c496ec217253136530ffba2fc20e02", "kind": "retraction", "origin": "middle_a", "first_consumer_detection_delay": 10, "issuer_detected_tick": 10, "consumer_detection_ticks": {"receiver_a": 20}}]`
停止原因：`[]`

## branch_retraction / recovery_ablation
错误完成 0/4；错误触达组织 0；恢复 1；查证 39。
检测记录：`[{"target": "60a2403c78be1bcac7eb376afa0d067be8c496ec217253136530ffba2fc20e02", "kind": "retraction", "origin": "middle_a", "first_consumer_detection_delay": 10, "issuer_detected_tick": 10, "consumer_detection_ticks": {"receiver_a": 20}}]`
停止原因：`[]`

## late_notice / autonomous
错误完成 2/4；错误触达组织 2；恢复 0；查证 0。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 10, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## late_notice / root_gate
错误完成 2/4；错误触达组织 2；恢复 0；查证 22。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 10, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## late_notice / simple_dependency_gate
错误完成 0/4；错误触达组织 0；恢复 2；查证 38。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 2, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 12, "middle_b": 12, "receiver_a": 20, "receiver_b": 20}}]`
停止原因：`[]`

## late_notice / dependency
错误完成 0/4；错误触达组织 0；恢复 2；查证 38。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 2, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 12, "middle_b": 12, "receiver_a": 20, "receiver_b": 20}}]`
停止原因：`[]`

## late_notice / dependency_push
错误完成 0/4；错误触达组织 0；恢复 2；查证 38。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 2, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 12, "middle_b": 12, "receiver_a": 20, "receiver_b": 20}}]`
停止原因：`[]`

## late_notice / verify_all
错误完成 0/4；错误触达组织 0；恢复 2；查证 38。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 2, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 12, "middle_b": 12, "receiver_a": 20, "receiver_b": 20}}]`
停止原因：`[]`

## late_notice / selective
错误完成 0/4；错误触达组织 2；恢复 2；查证 18。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 4, "issuer_detected_tick": 10, "consumer_detection_ticks": {"receiver_a": 14, "receiver_b": 14}}]`
停止原因：`[]`

## late_notice / recovery_ablation
错误完成 0/4；错误触达组织 0；恢复 2；查证 38。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 2, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 12, "middle_b": 12, "receiver_a": 20, "receiver_b": 20}}]`
停止原因：`[]`

## derived_error / autonomous
错误完成 0/4；错误触达组织 0；恢复 0；查证 0。
检测记录：`[{"target": "65d795860ad92632a0454ea0c552fe57fbe0cc01a25b50936ca8ed7dd34d415b", "kind": "derived_error", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 1, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## derived_error / root_gate
错误完成 0/4；错误触达组织 0；恢复 0；查证 14。
检测记录：`[{"target": "65d795860ad92632a0454ea0c552fe57fbe0cc01a25b50936ca8ed7dd34d415b", "kind": "derived_error", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 1, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## derived_error / simple_dependency_gate
错误完成 0/4；错误触达组织 0；恢复 0；查证 24。
检测记录：`[{"target": "65d795860ad92632a0454ea0c552fe57fbe0cc01a25b50936ca8ed7dd34d415b", "kind": "derived_error", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 1, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## derived_error / dependency
错误完成 0/4；错误触达组织 0；恢复 0；查证 24。
检测记录：`[{"target": "65d795860ad92632a0454ea0c552fe57fbe0cc01a25b50936ca8ed7dd34d415b", "kind": "derived_error", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 1, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## derived_error / dependency_push
错误完成 0/4；错误触达组织 0；恢复 0；查证 24。
检测记录：`[{"target": "65d795860ad92632a0454ea0c552fe57fbe0cc01a25b50936ca8ed7dd34d415b", "kind": "derived_error", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 1, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## derived_error / verify_all
错误完成 0/4；错误触达组织 0；恢复 0；查证 24。
检测记录：`[{"target": "65d795860ad92632a0454ea0c552fe57fbe0cc01a25b50936ca8ed7dd34d415b", "kind": "derived_error", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 1, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## derived_error / selective
错误完成 0/4；错误触达组织 0；恢复 0；查证 8。
检测记录：`[{"target": "65d795860ad92632a0454ea0c552fe57fbe0cc01a25b50936ca8ed7dd34d415b", "kind": "derived_error", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 1, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## derived_error / recovery_ablation
错误完成 0/4；错误触达组织 0；恢复 0；查证 24。
检测记录：`[{"target": "65d795860ad92632a0454ea0c552fe57fbe0cc01a25b50936ca8ed7dd34d415b", "kind": "derived_error", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 1, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## missing_dependency / autonomous
错误完成 0/4；错误触达组织 0；恢复 0；查证 0。
检测记录：`[{"target": "fdca754b859f465bab646514d1b788e66d45a75c3b440d2b909b922fd91a011e", "kind": "missing_dependency", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 1, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## missing_dependency / root_gate
错误完成 0/4；错误触达组织 0；恢复 0；查证 14。
检测记录：`[{"target": "fdca754b859f465bab646514d1b788e66d45a75c3b440d2b909b922fd91a011e", "kind": "missing_dependency", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 1, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## missing_dependency / simple_dependency_gate
错误完成 0/4；错误触达组织 0；恢复 0；查证 24。
检测记录：`[{"target": "fdca754b859f465bab646514d1b788e66d45a75c3b440d2b909b922fd91a011e", "kind": "missing_dependency", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 1, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## missing_dependency / dependency
错误完成 0/4；错误触达组织 0；恢复 0；查证 24。
检测记录：`[{"target": "fdca754b859f465bab646514d1b788e66d45a75c3b440d2b909b922fd91a011e", "kind": "missing_dependency", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 1, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## missing_dependency / dependency_push
错误完成 0/4；错误触达组织 0；恢复 0；查证 24。
检测记录：`[{"target": "fdca754b859f465bab646514d1b788e66d45a75c3b440d2b909b922fd91a011e", "kind": "missing_dependency", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 1, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## missing_dependency / verify_all
错误完成 0/4；错误触达组织 0；恢复 0；查证 24。
检测记录：`[{"target": "fdca754b859f465bab646514d1b788e66d45a75c3b440d2b909b922fd91a011e", "kind": "missing_dependency", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 1, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## missing_dependency / selective
错误完成 0/4；错误触达组织 0；恢复 0；查证 8。
检测记录：`[{"target": "fdca754b859f465bab646514d1b788e66d45a75c3b440d2b909b922fd91a011e", "kind": "missing_dependency", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 1, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## missing_dependency / recovery_ablation
错误完成 0/4；错误触达组织 0；恢复 0；查证 24。
检测记录：`[{"target": "fdca754b859f465bab646514d1b788e66d45a75c3b440d2b909b922fd91a011e", "kind": "missing_dependency", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 1, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## conflicting_sources / autonomous
错误完成 2/4；错误触达组织 5；恢复 0；查证 0。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "conflicting_sources", "origin": "source", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## conflicting_sources / root_gate
错误完成 2/4；错误触达组织 5；恢复 0；查证 22。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "conflicting_sources", "origin": "source", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## conflicting_sources / simple_dependency_gate
错误完成 2/4；错误触达组织 5；恢复 0；查证 42。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "conflicting_sources", "origin": "source", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## conflicting_sources / dependency
错误完成 2/4；错误触达组织 5；恢复 0；查证 42。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "conflicting_sources", "origin": "source", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## conflicting_sources / dependency_push
错误完成 2/4；错误触达组织 5；恢复 0；查证 42。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "conflicting_sources", "origin": "source", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## conflicting_sources / verify_all
错误完成 2/4；错误触达组织 5；恢复 0；查证 42。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "conflicting_sources", "origin": "source", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## conflicting_sources / selective
错误完成 2/4；错误触达组织 5；恢复 0；查证 16。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "conflicting_sources", "origin": "source", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## conflicting_sources / recovery_ablation
错误完成 2/4；错误触达组织 5；恢复 0；查证 42。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "conflicting_sources", "origin": "source", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## signed_false / autonomous
错误完成 2/4；错误触达组织 5；恢复 0；查证 0。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "signed_false", "origin": "source", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## signed_false / root_gate
错误完成 2/4；错误触达组织 5；恢复 0；查证 22。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "signed_false", "origin": "source", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## signed_false / simple_dependency_gate
错误完成 2/4；错误触达组织 5；恢复 0；查证 42。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "signed_false", "origin": "source", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## signed_false / dependency
错误完成 2/4；错误触达组织 5；恢复 0；查证 42。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "signed_false", "origin": "source", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## signed_false / dependency_push
错误完成 2/4；错误触达组织 5；恢复 0；查证 42。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "signed_false", "origin": "source", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## signed_false / verify_all
错误完成 2/4；错误触达组织 5；恢复 0；查证 42。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "signed_false", "origin": "source", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## signed_false / selective
错误完成 2/4；错误触达组织 5；恢复 0；查证 16。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "signed_false", "origin": "source", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## signed_false / recovery_ablation
错误完成 2/4；错误触达组织 5；恢复 0；查证 42。
检测记录：`[{"target": "d0cc249ca030d6f79faa1a262a634d47788c6c1ce917f3d78d2b83d35c2a4abd", "kind": "signed_false", "origin": "source", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## bad_recovery_binding / autonomous
错误完成 2/4；错误触达组织 2；恢复 0；查证 0。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 10, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## bad_recovery_binding / root_gate
错误完成 2/4；错误触达组织 2；恢复 0；查证 22。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 10, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## bad_recovery_binding / simple_dependency_gate
错误完成 0/4；错误触达组织 0；恢复 1；查证 34。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 2, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 12, "middle_b": 12, "receiver_a": 20, "receiver_b": 20}}, {"target": "9819bd076b4fc74148bd4e5a390ac0faeb7cc358db37ca52efc4c2a425717609", "kind": "bad_recovery_binding", "origin": "middle_a", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`["completion_evidence_rejected"]`

## bad_recovery_binding / dependency
错误完成 0/4；错误触达组织 0；恢复 1；查证 34。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 2, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 12, "middle_b": 12, "receiver_a": 20, "receiver_b": 20}}, {"target": "02d39559a5166e9dfd88024ee7cfed557dc528e4e3cdb1824656baf30cf59586", "kind": "bad_recovery_binding", "origin": "middle_a", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`["completion_evidence_rejected"]`

## bad_recovery_binding / dependency_push
错误完成 0/4；错误触达组织 0；恢复 1；查证 32。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 1, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 11, "middle_b": 11, "receiver_a": 20, "receiver_b": 20}}, {"target": "02d39559a5166e9dfd88024ee7cfed557dc528e4e3cdb1824656baf30cf59586", "kind": "bad_recovery_binding", "origin": "middle_a", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`["completion_evidence_rejected"]`

## bad_recovery_binding / verify_all
错误完成 0/4；错误触达组织 0；恢复 1；查证 34。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 2, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 12, "middle_b": 12, "receiver_a": 20, "receiver_b": 20}}, {"target": "9819bd076b4fc74148bd4e5a390ac0faeb7cc358db37ca52efc4c2a425717609", "kind": "bad_recovery_binding", "origin": "middle_a", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`["completion_evidence_rejected"]`

## bad_recovery_binding / selective
错误完成 0/4；错误触达组织 2；恢复 1；查证 14。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 4, "issuer_detected_tick": 10, "consumer_detection_ticks": {"receiver_a": 14, "receiver_b": 14}}, {"target": "67e58931ca15b0c980ddecabb385446b103178b103eff318db9f1ba4fc98ae20", "kind": "bad_recovery_binding", "origin": "middle_a", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`["completion_evidence_rejected"]`

## bad_recovery_binding / recovery_ablation
错误完成 0/4；错误触达组织 0；恢复 2；查证 36。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 1, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 11, "middle_b": 11, "receiver_a": 20, "receiver_b": 20}}, {"target": "02d39559a5166e9dfd88024ee7cfed557dc528e4e3cdb1824656baf30cf59586", "kind": "bad_recovery_binding", "origin": "middle_a", "first_consumer_detection_delay": null, "issuer_detected_tick": null, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## recovery_retraction / autonomous
错误完成 2/4；错误触达组织 2；恢复 0；查证 0。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 10, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## recovery_retraction / root_gate
错误完成 2/4；错误触达组织 2；恢复 0；查证 22。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": null, "issuer_detected_tick": 10, "consumer_detection_ticks": {}}]`
停止原因：`[]`

## recovery_retraction / simple_dependency_gate
错误完成 0/4；错误触达组织 0；恢复 1；查证 34。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 2, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 12, "middle_b": 12, "receiver_a": 20, "receiver_b": 20}}, {"target": "cfa3dcb0cd4b47825174456d763f0126abd812174e9984bbbe39d09aaaf8b83e", "kind": "recovery_retraction", "origin": "middle_a", "first_consumer_detection_delay": 0, "issuer_detected_tick": 20, "consumer_detection_ticks": {"receiver_a": 20}}]`
停止原因：`["recovery_requires_replan"]`

## recovery_retraction / dependency
错误完成 0/4；错误触达组织 0；恢复 1；查证 34。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 2, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 12, "middle_b": 12, "receiver_a": 20, "receiver_b": 20}}, {"target": "dbda835328b0a88e1f791e2c1ea8f4063497211a7fbdda17b31e370811bf4706", "kind": "recovery_retraction", "origin": "middle_a", "first_consumer_detection_delay": 0, "issuer_detected_tick": 20, "consumer_detection_ticks": {"receiver_a": 20}}]`
停止原因：`["recovery_requires_replan"]`

## recovery_retraction / dependency_push
错误完成 0/4；错误触达组织 0；恢复 1；查证 32。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 1, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 11, "middle_b": 11, "receiver_a": 20, "receiver_b": 20}}, {"target": "dbda835328b0a88e1f791e2c1ea8f4063497211a7fbdda17b31e370811bf4706", "kind": "recovery_retraction", "origin": "middle_a", "first_consumer_detection_delay": 0, "issuer_detected_tick": 20, "consumer_detection_ticks": {"receiver_a": 20}}]`
停止原因：`["recovery_requires_replan"]`

## recovery_retraction / verify_all
错误完成 0/4；错误触达组织 0；恢复 1；查证 34。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 2, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 12, "middle_b": 12, "receiver_a": 20, "receiver_b": 20}}, {"target": "cfa3dcb0cd4b47825174456d763f0126abd812174e9984bbbe39d09aaaf8b83e", "kind": "recovery_retraction", "origin": "middle_a", "first_consumer_detection_delay": 0, "issuer_detected_tick": 20, "consumer_detection_ticks": {"receiver_a": 20}}]`
停止原因：`["recovery_requires_replan"]`

## recovery_retraction / selective
错误完成 0/4；错误触达组织 2；恢复 1；查证 14。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 4, "issuer_detected_tick": 10, "consumer_detection_ticks": {"receiver_a": 14, "receiver_b": 14}}, {"target": "bdb4decff96ee21fa188205c10d87c7a058fc29f1c46c3f52a5b2e7ea47d013b", "kind": "recovery_retraction", "origin": "middle_a", "first_consumer_detection_delay": 0, "issuer_detected_tick": 20, "consumer_detection_ticks": {"receiver_a": 20}}]`
停止原因：`["recovery_requires_replan"]`

## recovery_retraction / recovery_ablation
错误完成 0/4；错误触达组织 0；恢复 1；查证 32。
检测记录：`[{"target": "17be570b9358bb979fcfa1ef845c24e4981f0076d4cb2b1ded7d61d589c9a133", "kind": "retraction", "origin": "coordinator", "first_consumer_detection_delay": 1, "issuer_detected_tick": 10, "consumer_detection_ticks": {"middle_a": 11, "middle_b": 11, "receiver_a": 20, "receiver_b": 20}}, {"target": "8e49ee6b6cbe76f67c0a83b3c0f3e15944a2f565de08dceb69898f9f41f8ad71", "kind": "recovery_retraction", "origin": "middle_a", "first_consumer_detection_delay": 0, "issuer_detected_tick": 20, "consumer_detection_ticks": {"receiver_a": 20}}]`
停止原因：`[]`

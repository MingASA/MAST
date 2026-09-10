"""Public derivation rules; no model prose or hidden organization state."""


def valid_derivation(rule, output, inputs):
    if rule=='relay': return all(fact==output for fact in inputs)
    if rule!='sum_charges': return False
    # A signed manifest defines completeness. Merely adding the disclosed
    # numbers is insufficient: an omitted charge must not become a valid total.
    manifests=[f for f in inputs if f.get('predicate')=='charge_manifest']
    if len(manifests)!=1: return False
    manifest=manifests[0]['value']
    if set(manifest)!={'order','currency','components'}: return False
    components=manifest['components']
    if not isinstance(components,list) or not components or not all(isinstance(c,str) and c for c in components): return False
    if len(set(components))!=len(components): return False
    charges=[f for f in inputs if f.get('predicate')!='charge_manifest']
    if len(charges)!=len(components): return False
    amounts={}
    for fact in charges:
        value=fact.get('value',{})
        if set(value)!={'order','currency','component','cents'}: return False
        if (value['order']!=manifest['order'] or value['currency']!=manifest['currency'] or
                type(value['cents']) is not int or value['cents']<0): return False
        component=value['component']
        if component not in components or component in amounts or fact['predicate']!='charge/'+component: return False
        amounts[component]=value['cents']
    return output=={'predicate':'total_charge','value':{'order':manifest['order'],
                    'currency':manifest['currency'],'cents':sum(amounts.values())}}


def relay_fact(gateway, parents, reference):
    """Resolve an explicit relay reference from available owner-local evidence.

    This is serialization, not fact discovery or an approval. Final signing or
    rebuilding must still validate the rule, dependencies and recovery binding.
    """
    import copy
    if (not isinstance(parents,list) or not parents or
            any(not isinstance(p,str) for p in parents) or
            len(set(parents))!=len(parents) or reference not in parents):
        raise ValueError('relay reference must identify a required parent')
    if any(gateway.blockers(p) for p in parents):
        raise ValueError('relay parent unavailable')
    facts=[gateway.claims[p]['body']['fact'] for p in parents]
    result=gateway.claims[reference]['body']['fact']
    if not valid_derivation('relay',result,facts):
        raise ValueError('relay parents disagree')
    return copy.deepcopy(result)


def proposed_fact(gateway, request, parents):
    """Legacy explicit fact or typed reference; never silently repair a draft."""
    if ('fact' in request)==('fact_ref' in request):
        raise ValueError('provide exactly one of fact or fact_ref')
    if 'fact_ref' in request:
        if request.get('rule','relay')!='relay':raise ValueError('reference requires relay')
        return relay_fact(gateway,parents,request['fact_ref'])
    return request['fact']

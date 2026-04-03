def format_dict_as_markdown(d, indent=0):
    lines = []
    spacer = "  " * indent
    if isinstance(d, dict):
        for k, v in d.items():
            human_key = str(k).replace("_", " ").title()
            
            if indent == 0:
                if isinstance(v, (dict, list)):
                    lines.append(f"#### {human_key}")
                    lines.extend(format_dict_as_markdown(v, indent + 1))
                    lines.append("")
                else:
                    lines.append(f"#### {human_key}")
                    lines.append(str(v))
                    lines.append("")
            else:
                if isinstance(v, dict):
                    lines.append(f"{spacer}- **{human_key}**:")
                    lines.extend(format_dict_as_markdown(v, indent + 1))
                elif isinstance(v, list):
                    lines.append(f"{spacer}- **{human_key}**:")
                    for item in v:
                        if isinstance(item, dict):
                            # Give a little spacing for list of dicts
                            sub_lines = format_dict_as_markdown(item, indent + 1)
                            if sub_lines:
                                sub_lines[0] = sub_lines[0].replace(f"{spacer}  -", f"{spacer}  *", 1) # minor style tweak to indicate item root
                            lines.extend(sub_lines)
                        else:
                            lines.append(f"{spacer}  - {item}")
                else:
                    lines.append(f"{spacer}- **{human_key}**: {v}")
    elif isinstance(d, list):
        for item in d:
            if isinstance(item, dict):
                lines.extend(format_dict_as_markdown(item, indent))
            else:
                lines.append(f"{spacer}- {item}")
    else:
        lines.append(f"{spacer}- {d}")
    return lines
